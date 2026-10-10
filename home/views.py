import json
import logging
import random
import string

from decimal import Decimal, getcontext
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Avg, Max, Q
from django.db.models.functions import TruncWeek, TruncMonth, TruncYear
from django.utils import timezone
from django.utils.http import urlencode
from django.core.mail import send_mail
from django.core.paginator import Paginator

from webauthn import (
    generate_registration_options,
    generate_authentication_options,
    verify_registration_response,
    verify_authentication_response,
)
from webauthn.helpers.structs import (
    RegistrationCredential,
    AuthenticationCredential,
    PublicKeyCredentialDescriptor,
)
from webauthn.helpers.exceptions import (
    InvalidRegistrationResponse,
    InvalidAuthenticationResponse,
)

# --- UPDATED IMPORTS FOR MODELS AND FORMS ---

from .models import (
    CustomUser,
    Transaction,
    Income,
    Budget,
    Goal,
    Profile,
    Category,
    RegisteredCredential,
)
from .forms import (
    ResetPasswordForm, ResetCodeForm, UserRegistrationForm, UserProfileEditForm,
    CategoryForm, TransactionForm, IncomeForm, BudgetForm, GoalForm
)
# --- END UPDATED IMPORTS ---
def get_financial_year_dates(start_year):
    """
    Return the start and end dates for an Indian financial year.
    Example: 2026 -> 2026-04-01 to 2027-03-31
    """
    start_year = int(start_year)

    fy_start = date(start_year, 4, 1)
    fy_end = date(start_year + 1, 3, 31)

    return fy_start, fy_end



def calculate_tax(
    gross_income,
    financial_year,
    is_salaried=False,
    opted_old_regime=False,
):
    """
    AY 2026-27 Indian income-tax calculator.

    Intended for an individual below 60 years of age.
    Calculates either the old or new regime.

    IMPORTANT:
    - gross_income is gross income before standard deduction.
    - Personal expenses are NOT treated as tax deductions.
    - Old-regime deductions such as 80C/80D are not included unless
      explicitly added later.
    """

    gross_income = Decimal(str(gross_income or "0"))

    if gross_income < Decimal("0"):
        gross_income = Decimal("0")

    # ---------------------------------------------------------
    # STANDARD DEDUCTION
    # ---------------------------------------------------------
    if is_salaried:
        standard_deduction = (
            Decimal("50000")
            if opted_old_regime
            else Decimal("75000")
        )
    else:
        standard_deduction = Decimal("0")

    taxable_income = max(
        Decimal("0"),
        gross_income - standard_deduction
    )

    # ---------------------------------------------------------
    # AY 2026-27 TAX SLABS
    # ---------------------------------------------------------
    if opted_old_regime:
        slabs = [
            (Decimal("250000"), Decimal("0.00")),
            (Decimal("250000"), Decimal("0.05")),
            (Decimal("500000"), Decimal("0.20")),
            (None, Decimal("0.30")),
        ]
        regime = "Old Regime"
    else:
        slabs = [
            (Decimal("400000"), Decimal("0.00")),
            (Decimal("400000"), Decimal("0.05")),
            (Decimal("400000"), Decimal("0.10")),
            (Decimal("400000"), Decimal("0.15")),
            (Decimal("400000"), Decimal("0.20")),
            (Decimal("400000"), Decimal("0.25")),
            (None, Decimal("0.30")),
        ]
        regime = "New Regime"

    # ---------------------------------------------------------
    # SLAB TAX
    # ---------------------------------------------------------
    remaining_income = taxable_income
    slab_tax = Decimal("0")

    for slab_limit, rate in slabs:
        if remaining_income <= Decimal("0"):
            break

        if slab_limit is None:
            slab_income = remaining_income
        else:
            slab_income = min(
                remaining_income,
                slab_limit
            )

        slab_tax += slab_income * rate
        remaining_income -= slab_income

    # ---------------------------------------------------------
    # SECTION 87A REBATE
    # ---------------------------------------------------------
    rebate = Decimal("0")

    if opted_old_regime:
        if taxable_income <= Decimal("500000"):
            rebate = min(
                slab_tax,
                Decimal("12500")
            )
    else:
        if taxable_income <= Decimal("1200000"):
            rebate = min(
                slab_tax,
                Decimal("60000")
            )

    tax_after_rebate = max(
        Decimal("0"),
        slab_tax - rebate
    )

    # ---------------------------------------------------------
    # NEW-REGIME MARGINAL RELIEF
    #
    # For taxable income just above ₹12 lakh.
    # ---------------------------------------------------------
    marginal_relief = Decimal("0")

    if (
        not opted_old_regime
        and taxable_income > Decimal("1200000")
        and taxable_income <= Decimal("1270588")
    ):
        excess_income = taxable_income - Decimal("1200000")

        if tax_after_rebate > excess_income:
            marginal_relief = (
                tax_after_rebate - excess_income
            )

            tax_after_rebate = excess_income

    # ---------------------------------------------------------
    # SURCHARGE
    # ---------------------------------------------------------
    if taxable_income <= Decimal("5000000"):
        surcharge_rate = Decimal("0")
    elif taxable_income <= Decimal("10000000"):
        surcharge_rate = Decimal("0.10")
    elif taxable_income <= Decimal("20000000"):
        surcharge_rate = Decimal("0.15")
    elif taxable_income <= Decimal("50000000"):
        surcharge_rate = Decimal("0.25")
    else:
        surcharge_rate = (
            Decimal("0.25")
            if not opted_old_regime
            else Decimal("0.37")
        )

    surcharge = (
        tax_after_rebate * surcharge_rate
    )

    # ---------------------------------------------------------
    # SURCHARGE MARGINAL RELIEF
    # ---------------------------------------------------------
    surcharge_marginal_relief = Decimal("0")

    surcharge_thresholds = [
        Decimal("5000000"),
        Decimal("10000000"),
        Decimal("20000000"),
    ]

    if opted_old_regime:
        surcharge_thresholds.append(
            Decimal("50000000")
        )

    for threshold in surcharge_thresholds:
        if taxable_income > threshold:
            excess_income = taxable_income - threshold

            threshold_tax_result = calculate_tax(
                threshold,
                financial_year,
                is_salaried=False,
                opted_old_regime=opted_old_regime,
            )

            threshold_tax = (
                threshold_tax_result["income_tax_after_rebate"]
                + threshold_tax_result["surcharge"]
            )

            tax_with_surcharge = (
                tax_after_rebate + surcharge
            )

            allowed_tax = threshold_tax + excess_income

            if tax_with_surcharge > allowed_tax:
                surcharge_marginal_relief = (
                    tax_with_surcharge - allowed_tax
                )

                surcharge = max(
                    Decimal("0"),
                    surcharge - surcharge_marginal_relief
                )

            break

    # ---------------------------------------------------------
    # HEALTH & EDUCATION CESS
    # ---------------------------------------------------------
    income_tax_after_rebate = tax_after_rebate

    tax_plus_surcharge = (
        income_tax_after_rebate + surcharge
    )

    cess = tax_plus_surcharge * Decimal("0.04")

    total_tax = (
        tax_plus_surcharge + cess
    )

    # Tax is normally rounded to nearest ₹10.
    total_tax = (
        (total_tax / Decimal("10"))
        .quantize(Decimal("1"))
        * Decimal("10")
    )

    # ---------------------------------------------------------
    # EFFECTIVE RATE / IN-HAND
    # ---------------------------------------------------------
    if taxable_income > Decimal("0"):
        tax_percentage = (
            total_tax / taxable_income
        ) * Decimal("100")
    else:
        tax_percentage = Decimal("0")

    in_hand_salary = max(
        Decimal("0"),
        gross_income - total_tax
    )

    monthly_tax = total_tax / Decimal("12")
    monthly_in_hand = in_hand_salary / Decimal("12")

    return {
        "gross_income": gross_income,
        "standard_deduction": standard_deduction,
        "taxable_income_after_deduction": taxable_income,

        "slab_tax": slab_tax,
        "rebate": rebate,

        "income_tax_after_rebate": income_tax_after_rebate,

        "marginal_relief": marginal_relief,

        "surcharge_rate": surcharge_rate,
        "surcharge": surcharge,
        "surcharge_marginal_relief": surcharge_marginal_relief,

        "cess": cess,

        "total_tax_amount": total_tax,

        "tax_percentage": tax_percentage.quantize(
            Decimal("0.01")
        ),

        "in_hand_salary": in_hand_salary,

        "monthly_tax": monthly_tax,
        "monthly_in_hand": monthly_in_hand,

        "regime": regime,

        "tax_rule_reference": (
            "AY 2026-27 / FY 2025-26"
        ),

        "calculation_scope": (
            "Normal slab-rate income estimate. "
            "Special-rate income and additional "
            "deductions/exemptions are not included."
        ),
    }


User = CustomUser
getcontext().prec = 10
logger = logging.getLogger(__name__)

# Temporary in-memory store (replace with a DB in production)
USERS = {}  # {username: {"id": b"...", "public_key": b"...", "sign_count": int}}


# -------------------- WEB AUTHN VIEWS -------------------- #

@csrf_exempt
def begin_registration(request):
    """Step 1: Send registration options to frontend"""
    body = json.loads(request.body)
    username = body.get("username")
    if not username:
        return JsonResponse({"error": "Username required"}, status=400)

    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=username.encode("utf-8"),
        user_name=username,
    )

    request.session["challenge"] = options.challenge
    return JsonResponse(options.model_dump())


@csrf_exempt
def finish_registration(request):
    """Step 2: Verify registration response"""
    body = json.loads(request.body)
    username = body.get("username")
    if not username:
        return JsonResponse({"error": "Username required"}, status=400)

    try:
        # Pass the raw JSON body to the 'response' parameter.
        verification = verify_registration_response(
            response=body,
            expected_challenge=request.session.get("challenge"),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
        )

        USERS[username] = {
            "id": verification.credential_id,
            "public_key": verification.credential_public_key,
            "sign_count": verification.sign_count,
        }

        return JsonResponse({"status": "ok"})

    except InvalidRegistrationResponse as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)


@csrf_exempt
def begin_authentication(request):
    """Step 3: Send authentication options to frontend"""
    body = json.loads(request.body)
    username = body.get("username")
    if not username or username not in USERS:
        return JsonResponse({"error": "User not found"}, status=404)

    user_cred = USERS[username]

    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[PublicKeyCredentialDescriptor(id=user_cred["id"])],
    )

    request.session["challenge"] = options.challenge
    return JsonResponse(options.model_dump())


@csrf_exempt
def finish_authentication(request):
    """Step 4: Verify authentication response"""
    body = json.loads(request.body)
    username = body.get("username")
    if not username or username not in USERS:
        return JsonResponse({"error": "User not found"}, status=404)

    user_cred = USERS[username]

    try:
        # Pass the raw JSON body to the 'response' parameter.
        verification = verify_authentication_response(
            response=body,
            expected_challenge=request.session.get("challenge"),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGIN,
            credential_public_key=user_cred["public_key"],
            credential_current_sign_count=user_cred["sign_count"],
        )

        # Update sign count after successful authentication
        USERS[username]["sign_count"] = verification.new_sign_count
        return JsonResponse({"status": "ok"})

    except InvalidAuthenticationResponse as e:
        return JsonResponse({"error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"error": f"An unexpected error occurred: {str(e)}"}, status=500)

@csrf_exempt
@login_required
def calculate_taxation(request):
    """
    Taxation comparison endpoint.

    Returns BOTH:
      - New Tax Regime
      - Old Tax Regime

    so the UI can recommend the lower-tax option.
    """

    if request.method != "POST":
        return JsonResponse(
            {"error": "Invalid request method"},
            status=405
        )

    try:
        data = json.loads(request.body)
        calculation_type = data.get("calculation_type")
        user = request.user

        # -----------------------------------------------------
        # Helper
        # -----------------------------------------------------
        def serialize_tax_result(result):
            return {
                key: float(value)
                if isinstance(value, Decimal)
                else value
                for key, value in result.items()
            }

        # -----------------------------------------------------
        # ANNUAL SALARY
        # -----------------------------------------------------
        if calculation_type == "annual_estimate":

            annual_salary_gross = Decimal(
                str(data.get("annual_salary", "0"))
            )

            if annual_salary_gross < 0:
                return JsonResponse(
                    {"error": "Annual salary cannot be negative."},
                    status=400
                )

            today = timezone.now().date()

            fy_start_year = (
                today.year
                if today.month >= 4
                else today.year - 1
            )

            current_fy_string = (
                f"{fy_start_year}-{fy_start_year + 1}"
            )

            new_regime = calculate_tax(
                annual_salary_gross,
                current_fy_string,
                is_salaried=True,
                opted_old_regime=False,
            )

            old_regime = calculate_tax(
                annual_salary_gross,
                current_fy_string,
                is_salaried=True,
                opted_old_regime=True,
            )

            if (
                new_regime["total_tax_amount"]
                <= old_regime["total_tax_amount"]
            ):
                recommended = "New Regime"
                savings = (
                    old_regime["total_tax_amount"]
                    - new_regime["total_tax_amount"]
                )
            else:
                recommended = "Old Regime"
                savings = (
                    new_regime["total_tax_amount"]
                    - old_regime["total_tax_amount"]
                )

            return JsonResponse({
                "calculation_type": "annual_estimate",

                "tax_year": "AY 2026-27",
                "financial_year": "FY 2025-26",

                "gross_income": float(
                    annual_salary_gross
                ),

                "recommended_regime": recommended,

                "tax_saving": float(savings),

                "new_regime": serialize_tax_result(
                    new_regime
                ),

                "old_regime": serialize_tax_result(
                    old_regime
                ),
            })

        # -----------------------------------------------------
        # PERIOD
        # -----------------------------------------------------
        elif calculation_type == "period":

            start_date_str = data.get("start_date")
            end_date_str = data.get("end_date")

            if not start_date_str or not end_date_str:
                return JsonResponse(
                    {"error": "Start date and end date are required."},
                    status=400
                )

            start_date = date.fromisoformat(
                start_date_str
            )

            end_date = date.fromisoformat(
                end_date_str
            )

            min_end_date = (
                start_date
                + relativedelta(months=+1)
            )

            if end_date < min_end_date:
                return JsonResponse(
                    {
                        "error":
                        "End date must be at least one month "
                        "after the start date."
                    },
                    status=400
                )

            # -------------------------------------------------
            # CASH FLOW
            # -------------------------------------------------
            total_income_period = (
                Income.objects
                .filter(
                    user=user,
                    date__gte=start_date,
                    date__lte=end_date,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            total_expense_period = (
                Transaction.objects
                .filter(
                    user=user,
                    date__gte=start_date,
                    date__lte=end_date,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            period_net_income = (
                total_income_period
                - total_expense_period
            )

            # -------------------------------------------------
            # CURRENT FY
            # -------------------------------------------------
            fy_start_year = (
                end_date.year
                if end_date.month >= 4
                else end_date.year - 1
            )

            current_fy_string = (
                f"{fy_start_year}-{fy_start_year + 1}"
            )

            current_fy_start, current_fy_end = (
                get_financial_year_dates(
                    str(fy_start_year)
                )
            )

            current_fy_total_income = (
                Income.objects
                .filter(
                    user=user,
                    date__gte=current_fy_start,
                    date__lte=current_fy_end,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            current_fy_total_expense = (
                Transaction.objects
                .filter(
                    user=user,
                    date__gte=current_fy_start,
                    date__lte=current_fy_end,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            # IMPORTANT:
            # Expenses are shown for cash-flow purposes.
            # They are NOT automatically deducted from taxable income.
            current_taxable_gross = (
                current_fy_total_income
            )

            current_new = calculate_tax(
                current_taxable_gross,
                current_fy_string,
                is_salaried=False,
                opted_old_regime=False,
            )

            current_old = calculate_tax(
                current_taxable_gross,
                current_fy_string,
                is_salaried=False,
                opted_old_regime=True,
            )

            # -------------------------------------------------
            # PREVIOUS FY
            # -------------------------------------------------
            previous_fy_start_year = (
                fy_start_year - 1
            )

            previous_fy_string = (
                f"{previous_fy_start_year}-"
                f"{previous_fy_start_year + 1}"
            )

            previous_fy_start, previous_fy_end = (
                get_financial_year_dates(
                    str(previous_fy_start_year)
                )
            )

            previous_fy_total_income = (
                Income.objects
                .filter(
                    user=user,
                    date__gte=previous_fy_start,
                    date__lte=previous_fy_end,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            previous_fy_total_expense = (
                Transaction.objects
                .filter(
                    user=user,
                    date__gte=previous_fy_start,
                    date__lte=previous_fy_end,
                )
                .aggregate(
                    Sum("amount")
                )["amount__sum"]
                or Decimal("0")
            )

            previous_new = calculate_tax(
                previous_fy_total_income,
                previous_fy_string,
                is_salaried=False,
                opted_old_regime=False,
            )

            previous_old = calculate_tax(
                previous_fy_total_income,
                previous_fy_string,
                is_salaried=False,
                opted_old_regime=True,
            )

            if (
                current_new["total_tax_amount"]
                <= current_old["total_tax_amount"]
            ):
                recommended = "New Regime"
                savings = (
                    current_old["total_tax_amount"]
                    - current_new["total_tax_amount"]
                )
            else:
                recommended = "Old Regime"
                savings = (
                    current_new["total_tax_amount"]
                    - current_old["total_tax_amount"]
                )

            return JsonResponse({
                "calculation_type": "period",

                "tax_year": "AY 2026-27",
                "financial_year": current_fy_string,

                "period_net_income": float(
                    period_net_income
                ),

                "period_income": float(
                    total_income_period
                ),

                "period_expenses": float(
                    total_expense_period
                ),

                "current_fy_income": float(
                    current_fy_total_income
                ),

                "current_fy_expenses": float(
                    current_fy_total_expense
                ),

                "previous_fy_income": float(
                    previous_fy_total_income
                ),

                "previous_fy_expenses": float(
                    previous_fy_total_expense
                ),

                "recommended_regime": recommended,

                "tax_saving": float(savings),

                "current_fy": {
                    "new_regime": serialize_tax_result(
                        current_new
                    ),
                    "old_regime": serialize_tax_result(
                        current_old
                    ),
                },

                "previous_fy": {
                    "new_regime": serialize_tax_result(
                        previous_new
                    ),
                    "old_regime": serialize_tax_result(
                        previous_old
                    ),
                },

                "tax_note": (
                    "Tracked expenses are shown as cash-flow "
                    "expenses and are not automatically treated "
                    "as income-tax deductions."
                ),
            })

        else:
            return JsonResponse(
                {"error": "Invalid calculation type"},
                status=400
            )

    except json.JSONDecodeError:
        return JsonResponse(
            {"error": "Invalid JSON payload"},
            status=400
        )

    except ValueError as e:
        return JsonResponse(
            {
                "error":
                f"Invalid input value or date format: {str(e)}"
            },
            status=400
        )

    except Exception as e:
        logger.error(
            "Unexpected error in calculate_taxation: %s",
            e,
            exc_info=True,
        )

        return JsonResponse(
            {
                "error":
                f"An internal server error occurred: {str(e)}"
            },
            status=500
        )


# --- NEW CATEGORY MANAGEMENT VIEWS (FULLY INTEGRATED) ---

@login_required
def add_category_view(request):
    """
    Handles adding new user-defined categories.
    The form is initialized with the request to filter choices if needed in the form itself.
    """
    if request.method == 'POST':
        # CHANGES: Pass 'request=request' to the form for user-specific validation/filtering
        form = CategoryForm(request.POST, request=request)
        if form.is_valid():
            category_name = form.cleaned_data['name']
            category_type = form.cleaned_data['type']

            duplicate_exists = Category.objects.filter(
                user=request.user,
                name=category_name,
                type=category_type,
            ).exists()

            if duplicate_exists:
                form.add_error(
                    'name',
                    'You already have a category with this name and type.',
                )
                messages.error(request, 'This category already exists.')
            else:
                category = form.save(commit=False)
                category.user = request.user
                category.save()
                messages.success(
                    request,
                    f"Category '{category.name}' added successfully!",
                )
                return redirect('list_categories')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form when rendering for GET request
        form = CategoryForm(request=request)

    expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')
    income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')
    budget_categories = Category.objects.filter(
        user=request.user,
        type__in=['expense', 'budget']
    ).order_by('name')
    goal_categories = Category.objects.filter(
        user=request.user,
        type__in=['goal', 'savings', 'investments']
    ).order_by('name')

    # Fetch categories for displaying in the template, categorized by type


    return render(request, 'home/manage_categories.html', {
        'form': form,
        'expense_categories': expense_categories,
        'income_categories': income_categories,
        'budget_categories': budget_categories,
        'goal_categories': goal_categories,
        'active_tab': 'add' # For UI to highlight the active tab
    })

@login_required
def list_categories_view(request):
    """
    Displays a list of all user-defined categories, separated by type.
    """
    expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')
    income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')
    budget_categories = Category.objects.filter(
        user=request.user,
        type__in=['expense', 'budget']
    ).order_by('name')
    goal_categories = Category.objects.filter(
        user=request.user,
        type__in=['goal', 'savings', 'investments']
    ).order_by('name')

    return render(request, 'home/manage_categories.html', {
        'expense_categories': expense_categories,
        'income_categories': income_categories,
        'budget_categories': budget_categories,
        'goal_categories': goal_categories,
        'active_tab': 'list' # For UI to highlight the active tab
    })

@login_required
def edit_category_view(request, category_id):
    """
    Handles editing an existing user-defined category.
    """
    category = get_object_or_404(Category, id=category_id, user=request.user)

    if request.method == 'POST':
        # CHANGES: Pass 'request=request' to the form for user-specific validation/filtering
        form = CategoryForm(request.POST, instance=category, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated successfully!")
            return redirect('list_categories')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form when rendering for GET request
        form = CategoryForm(instance=category, request=request)

    return render(request, 'home/edit_category.html', {
        'form': form,
        'category': category
    })

@login_required
def delete_category_view(request, category_id):
    """
    Handles deleting an existing user-defined category.
    """
    category = get_object_or_404(Category, id=category_id, user=request.user)
    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted successfully!")
        return redirect('list_categories')
    return render(request, 'home/confirm_delete_category.html', {'category': category})

# --- MODIFIED EXISTING VIEWS TO USE CATEGORIES AND FORMS ---

@login_required
def home_view(request):
    """
    Main dashboard view, displaying recent data and chart analytics.
    Integrated with user-defined categories for filtering and charting.
    """
    # Fetch recent items (unchanged core logic)
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')[:5]
    incomes = Income.objects.filter(user=request.user).order_by('-date')[:5]
    budgets = Budget.objects.filter(user=request.user).order_by('-id')[:5]
    goals = Goal.objects.filter(user=request.user).order_by('-id')[:5]

    # Chart data filtering parameters (unchanged core logic)
    selected_type = request.GET.get('data_type', 'income')
    time_period = request.GET.get('time_period', 'monthly')
    chart_type = request.GET.get('chart_type', 'overtime')
    selected_category_id_chart = request.GET.get('chart_category', '') # NEW: For chart specific category filter

    # Base queryset based on selected_type
    if selected_type == 'expense':
        queryset = Transaction.objects.filter(user=request.user)
    elif selected_type == 'budget':
        queryset = Budget.objects.filter(user=request.user)
    elif selected_type == 'goal':
        queryset = Goal.objects.filter(user=request.user)
    else: # Default to income
        queryset = Income.objects.filter(user=request.user)

    # Apply chart category filter if selected
    if selected_category_id_chart:
        try:
            selected_category_id_chart = int(selected_category_id_chart)
            # Apply category filter based on the type of data
            if selected_type in ['income', 'expense']:
                queryset = queryset.filter(category__id=selected_category_id_chart)
            elif selected_type == 'budget':
                queryset = queryset.filter(category__id=selected_category_id_chart)
            elif selected_type == 'goal':
                queryset = queryset.filter(category__id=selected_category_id_chart)
        except ValueError:
            pass # Invalid ID, ignore filter


    today = timezone.now().date()

    # Time period filtering for relevant models (unchanged core logic)
    if time_period == 'weekly':
        start_date = today - timedelta(days=6)
    elif time_period == 'yearly':
        start_date = today.replace(month=1, day=1)
    else: # monthly
        start_date = today.replace(day=1)

    if selected_type in ['income', 'expense']:
        queryset = queryset.filter(date__gte=start_date, date__lte=today)
    elif selected_type == 'goal':
        queryset = queryset.filter(
            deadline__gte=start_date,
            deadline__lte=today,
        )

    # Field to aggregate based on selected_type (unchanged core logic)
    if selected_type == 'budget':
        field_to_aggregate = 'limit'
    elif selected_type == 'goal':
        field_to_aggregate = 'target_amount'
    else:
        field_to_aggregate = 'amount'

    # Aggregations for summary stats (unchanged core logic)
    total = queryset.aggregate(total=Sum(field_to_aggregate))['total'] or Decimal('0.00')
    avg = queryset.aggregate(avg=Avg(field_to_aggregate))['avg'] or Decimal('0.00')
    mx = queryset.aggregate(mx=Max(field_to_aggregate))['mx'] or Decimal('0.00')

    chart_labels = []
    chart_data = []

    # Chart data generation logic (MODIFIED for category__name)
    if selected_type in ['income', 'expense']:
        if chart_type == 'overtime':
            if time_period == 'weekly':
                aggregation_func = TruncWeek('date')
                date_format_str = "%b %d, %Y" # Added Year for clarity
            elif time_period == 'yearly':
                aggregation_func = TruncMonth('date')
                date_format_str = "%b %Y"
            else: # Monthly
                aggregation_func = TruncMonth('date')
                date_format_str = "%b %Y"

            qs_chart = (
                queryset.annotate(period=aggregation_func)
                .values('period')
                .annotate(total=Sum('amount'))
                .order_by('period')
            )
            chart_labels = [entry['period'].strftime(date_format_str) for entry in qs_chart]
            chart_data = [float(entry['total']) for entry in qs_chart]

        elif chart_type == 'category':
            qs_chart = (
                queryset
                .values('category__name') # CHANGES: Use category__name for grouping
                .annotate(total=Sum('amount'))
                .order_by('category__name') # CHANGES: Order by category__name
            )
            chart_labels = [entry['category__name'] if entry['category__name'] else 'Uncategorized' for entry in qs_chart]
            chart_data = [float(entry['total']) for entry in qs_chart]

    elif selected_type == 'goal':
        if chart_type == 'category':
            qs_chart = (
            queryset
            .values('category__name')
            .annotate(total=Sum('target_amount'))
            .order_by('category__name')
        )
        chart_labels = [
            entry['category__name']
            if entry['category__name']
            else 'Uncategorized'
            for entry in qs_chart
        ]
        chart_data = [
            float(entry['total'])
            for entry in qs_chart
        ]

    elif selected_type == 'goal' and chart_type == 'overtime':
        if time_period == 'weekly':
            aggregation_func = TruncWeek('deadline')
            date_format_str = "%b %d, %Y"
        else:
            aggregation_func = TruncMonth('deadline')
            date_format_str = "%b %Y"

        qs_chart = (
            queryset
            .annotate(period=aggregation_func)
            .values('period')
            .annotate(total=Sum('target_amount'))
            .order_by('period')
        )

        chart_labels = [
            entry['period'].strftime(date_format_str)
            for entry in qs_chart
        ]

        chart_data = [
            float(entry['total'])
            for entry in qs_chart
        ]

    elif selected_type == 'budget':
     if chart_type == 'category':
        qs_chart = (
            queryset
            .values('category__name')
            .annotate(total=Sum('limit'))
            .order_by('category__name')
        )
        chart_labels = [
            entry['category__name']
            if entry['category__name']
            else 'Uncategorized'
            for entry in qs_chart
        ]
        chart_data = [
            float(entry['total'])
            for entry in qs_chart
        ]

    elif chart_type == 'overtime':
        if time_period == 'weekly':
            aggregation_func = TruncWeek('date')
            date_format_str = "%b %d, %Y"
        else:
            aggregation_func = TruncMonth('date')
            date_format_str = "%b %Y"

        qs_chart = (
            queryset
            .annotate(period=aggregation_func)
            .values('period')
            .annotate(total=Sum('limit'))
            .order_by('period')
        )

        chart_labels = [
            entry['period'].strftime(date_format_str)
            for entry in qs_chart
        ]

        chart_data = [
            float(entry['total'])
            for entry in qs_chart
        ]

    # Overall financial summaries (unchanged core logic)
    total_income_overall = Income.objects.filter(user=request.user).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_expenses_overall = Transaction.objects.filter(user=request.user).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_balance_overall = total_income_overall - total_expenses_overall

    monthly_spending = Transaction.objects.filter(
        user=request.user,
        date__year=today.year,
        date__month=today.month
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    total_budget_limit = Budget.objects.filter(
        user=request.user,
        date__year=today.year,
        date__month=today.month,
    ).aggregate(
        Sum('limit')
    )['limit__sum'] or Decimal('0.00')

    remaining_budget = total_budget_limit - monthly_spending

    # --- FIX FOR FieldError: Cannot resolve keyword 'type' into field ---
    # The 'type' field does not exist on the Transaction model.
    # Removing this filter. Upcoming bills will now sum all transactions
    # in the next 30 days that are dated in the future.
    upcoming_bills_amount = Transaction.objects.filter(
        user=request.user,
        date__gt=today,
        date__lte=today + timedelta(days=30)
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    # --- END FIX ---

    # Fetch categories for chart filtering dropdowns
    all_expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')
    all_income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')
    all_budget_categories = Category.objects.filter(user=request.user, type__in=['expense', 'budget']).order_by('name')
    all_goal_categories = Category.objects.filter(user=request.user, type__in=['goal', 'savings', 'investments']).order_by('name')


    return render(request, 'home/home.html', {
        'transactions': transactions,
        'incomes': incomes,
        'budgets': budgets,
        'goals': goals,
        'total_balance': total_balance_overall,
        'total_income': total_income_overall,
        'avg_income': Income.objects.filter(user=request.user).aggregate(Avg('amount'))['amount__avg'] or Decimal('0.00'),
        'max_income': Income.objects.filter(user=request.user).aggregate(Max('amount'))['amount__max'] or Decimal('0.00'),
        'total_expenses': total_expenses_overall,
        'monthly_spending': monthly_spending,
        'remaining_budget': remaining_budget,
        'upcoming_bills': upcoming_bills_amount,
        # Pass JSON-dumped strings to the template
        'chart_labels_json': json.dumps(chart_labels),
        'chart_data_json': json.dumps(chart_data),
        'selected_type_json': json.dumps(selected_type),
        'chart_type_json': json.dumps(chart_type),
        'time_period': time_period, # This is passed as a string, not for JSON parsing
        'selected_type': selected_type, # This is passed as a string, not for JSON parsing
        'chart_type': chart_type, # This is passed as a string, not for JSON parsing
        'total': total,
        'avg': avg,
        'mx': mx,
        'all_expense_categories': all_expense_categories,
        'all_income_categories': all_income_categories,
        'all_budget_categories': all_budget_categories,
        'all_goal_categories': all_goal_categories,
        'selected_category_id_chart': selected_category_id_chart,
    })

# --- USER AUTHENTICATION AND PROFILE VIEWS (CORE LOGIC - UNCHANGED) ---


def login_view(request):
    show_password_form = request.GET.get('form') == 'password'

    # ---------------------- HANDLE POST ----------------------
    if request.method == 'POST':

        # If JSON → WebAuthn request
        if request.content_type == 'application/json':
            body = json.loads(request.body)
            action = body.get('action')

            # -------- WebAuthn Registration --------
            if action == 'register':
                if not request.user.is_authenticated:
                    return JsonResponse({'error': 'User not authenticated'}, status=401)

                try:
                    credential = verify_registration_response(
                        response=body,
                        expected_challenge=request.session.get("challenge"),
                        expected_rp_id=settings.WEBAUTHN_RP_ID,
                        expected_origin=settings.WEBAUTHN_ORIGIN,
                    )

                    RegisteredCredential.objects.create(
                        user=request.user,
                        credential_id=credential.credential_id,
                        public_key=credential.credential_public_key,
                        sign_count=credential.sign_count,
                    )

                    return JsonResponse({'message': 'Registration successful!'})

                except InvalidRegistrationResponse as e:
                    return JsonResponse({'error': str(e)}, status=400)

            # -------- WebAuthn Authentication --------
            elif action == 'authenticate':
                try:
                    credential = verify_authentication_response(
                        response=body,
                        expected_challenge=request.session.get("challenge"),
                        expected_rp_id=settings.WEBAUTHN_RP_ID,
                        expected_origin=settings.WEBAUTHN_ORIGIN,
                        credential_public_key=body.get("publicKey"),
                        credential_current_sign_count=body.get("signCount"),
                    )

                    user = CustomUser.objects.get(id=int(body.get("user_id")))
                    login(request, user)

                    return JsonResponse({
                        'message': 'Authentication successful!',
                        'redirect_url': reverse('home')
                    })

                except InvalidAuthenticationResponse as e:
                    return JsonResponse({'error': str(e)}, status=400)
                except CustomUser.DoesNotExist:
                    return JsonResponse({'error': 'User not found'}, status=404)

        # -------- Password Login (Normal Form) --------
        else:
            username = request.POST.get('username')
            password = request.POST.get('password')

            if username and password:
                user = authenticate(request, username=username, password=password)

                if user:
                    login(request, user)
                    messages.success(request, "Login successful!")
                    return redirect('home')
                else:
                    messages.error(request, "Invalid username or password.")

    # ---------------------- HANDLE GET ----------------------
    authentication_options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID
    )

    try:
        authentication_options_json = json.dumps(authentication_options.model_dump())
    except AttributeError:
        authentication_options_json = json.dumps({})

    return render(request, 'home/login.html', {
        'show_password_form': show_password_form,
        'authentication_options': authentication_options_json,
    })
@login_required
def edit_profile_view(request):
    user = request.user
    if request.method == 'POST':
        user_form = UserProfileEditForm(request.POST, instance=user)
        if user_form.is_valid():
            user_form.save()
            messages.success(request, 'Your profile was successfully updated!')
            return redirect('view_profile')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        user_form = UserProfileEditForm(instance=user)
    context = {
        'user_form': user_form,
    }
    return render(request, 'home/edit_profile.html', context)

@login_required
def view_profile(request):
    context = {
        'user': request.user,
    }
    return render(request, 'home/profile.html', context)

def reset_password_view(request):
    if request.method == 'POST':
        form = ResetPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            reset_code = ''.join(random.choices(string.digits, k=6))
            try:
                profile = Profile.objects.get(user__email=email)
                profile.reset_code = reset_code
                profile.reset_code_created_at = timezone.now()
                profile.save(update_fields=['reset_code', 'reset_code_created_at'])
            except Profile.DoesNotExist:
                messages.error(request, "No user associated with this email address.")
                return redirect('reset_password')
            send_mail(
                'Your Password Reset Code',
                f'Your password reset code is: {reset_code}\n\nPlease use this code on the verification page to set a new password.',
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
            messages.success(request, "A password reset code has been sent to your email address.")
            return redirect('verify_reset_code')
        else:
            messages.error(request, "Please correct the errors below.")
    else:
        form = ResetPasswordForm()
    return render(request, 'home/reset_password.html', {'form': form})

def verify_reset_code_view(request):
    if request.method == 'POST':
        form = ResetCodeForm(request.POST)
        if form.is_valid():
            reset_code = form.cleaned_data['reset_code']
            new_password = form.cleaned_data['new_password']
            try:
                profile = Profile.objects.get(reset_code=reset_code)
                expiry_time = timezone.now() - timedelta(minutes=15)
                if not profile.reset_code_created_at or profile.reset_code_created_at < expiry_time:
                    profile.reset_code = ''
                    profile.reset_code_created_at = None
                    profile.save(update_fields=['reset_code', 'reset_code_created_at'])
                    messages.error(request, 'This reset code has expired. Please request a new one.')
                else:
                    user = profile.user
                    user.set_password(new_password)
                    user.save()
                    profile.reset_code = ''
                    profile.reset_code_created_at = None
                    profile.save(update_fields=['reset_code', 'reset_code_created_at'])
                    messages.success(request, 'Password reset successfully. You can now log in with your new password.')
                    return redirect('login')
            except Profile.DoesNotExist:
                messages.error(request, 'Invalid reset code. Please try again.')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ResetCodeForm()
    return render(request, 'home/verify_reset_code.html', {'form': form})

def register_view(request):
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            # Create the CustomUser instance
            user = CustomUser(
                username=form.cleaned_data['username'],
                email=form.cleaned_data['email'],
            )
            user.set_password(form.cleaned_data['password'])
            user.save()
            # The Profile should be created automatically by the post_save signal in models.py
            messages.success(request, 'Registration successful! Please login.')
            return redirect('login')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserRegistrationForm()
    return render(request, 'home/register.html', {'form': form})

@login_required
def add_expense_view(request):
    """
    Handles adding new expenses, integrated with user-defined categories.
    Includes filtering and charting based on category.
    """
    from django.db.models import Sum as DjangoSum

    if request.method == 'POST':
        # CHANGES: Pass 'request=request' to the form to filter category choices
        form = TransactionForm(request.POST, request=request)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user # Assign the current user to the transaction
            transaction.save()
            messages.success(request, 'Expense added successfully!')
            return redirect('add_expense')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form for GET request (initial display)
        form = TransactionForm(request=request)

    # Filtering and grouping logic for displaying expenses and charts
    selected_category_id = request.GET.get('selected_category_id', '')
    group_by = request.GET.get('group_by', 'monthly')

    # Recent Expenses always shows the user's latest expenses.
    recent_expenses = (
        Transaction.objects
        .filter(user=request.user)
        .select_related('category')
        .order_by('-date', '-id')
    )

    # Analytics queryset can be filtered independently.
    analytics_expenses = (
        Transaction.objects
        .filter(user=request.user)
        .select_related('category')
        .order_by('-date', '-id')
    )

    if selected_category_id:
        try:
            selected_category_id = int(selected_category_id)

            analytics_expenses = analytics_expenses.filter(
                category__id=selected_category_id,
                category__user=request.user,
                category__type='expense'
            )
        except (TypeError, ValueError):
            selected_category_id = ''

    if group_by == 'weekly':
        expenses_grouped = analytics_expenses.annotate(
            period=TruncWeek('date')
        )
    elif group_by == 'yearly':
        expenses_grouped = analytics_expenses.annotate(
            period=TruncYear('date')
        )
    else:
        expenses_grouped = analytics_expenses.annotate(
            period=TruncMonth('date')
        )

    grouped_totals = (
        expenses_grouped
        .values('period')
        .annotate(total=DjangoSum('amount'))
        .order_by('period')
    )

    labels = []
    values = []
    for item in grouped_totals:
        if group_by == 'weekly':
            labels.append(item['period'].strftime("Week %W, %Y"))
        elif group_by == 'monthly':
            labels.append(item['period'].strftime("%B %Y"))
        elif group_by == 'yearly':
            labels.append(str(item['period'].year))
        values.append(float(item['total']))

    # User-owned expense categories only
    has_chart_data = bool(values)

    all_expense_categories = (
        Category.objects
        .filter(user=request.user, type='expense')
        .order_by('name')
    )

    # ---------------------------------------------------------
    # Command-center analytics
    # ---------------------------------------------------------

    from django.db.models import Q, Count

    current_month = timezone.now().date().replace(day=1)

    # Combine total expenses, current-month expenses,
    # and expense count into a single database query.
    expense_metrics = Transaction.objects.filter(
        user=request.user
    ).aggregate(
        total=DjangoSum('amount'),
        monthly=DjangoSum(
            'amount',
            filter=Q(date__gte=current_month)
        ),
        count=Count('id'),
    )

    total_expenses = (
        expense_metrics['total']
        or Decimal('0.00')
    )

    monthly_expenses = (
        expense_metrics['monthly']
        or Decimal('0.00')
    )

    expense_count = expense_metrics['count']

    top_category = (
        Transaction.objects
        .filter(
            user=request.user,
            category__isnull=False
        )
        .values('category__name')
        .annotate(total=DjangoSum('amount'))
        .order_by('-total')
        .first()
    )

    top_category_name = (
        top_category['category__name']
        if top_category
        else 'No spending yet'
    )

    top_category_total = (
        top_category['total']
        if top_category
        else Decimal('0.00')
    )

    return render(request, 'home/add_expense.html', {
        'form': form,
        'expenses': recent_expenses[:5],

        # Existing chart functionality
        'category_labels': json.dumps(labels),
        'category_values': json.dumps(values),
        'has_chart_data': has_chart_data,

        # Existing category functionality
        'all_expense_categories': all_expense_categories,
        'selected_category_id': selected_category_id,
        'group_by': group_by,

        # New UI analytics
        'total_expenses': total_expenses,
        'monthly_expenses': monthly_expenses,
        'expense_count': expense_count,
        'top_category_name': top_category_name,
        'top_category_total': top_category_total,
    })

@login_required
def edit_expense_view(request, expense_id):
    """
    Handles editing an existing expense, integrated with user-defined categories.
    """
    expense = get_object_or_404(Transaction, id=expense_id, user=request.user)
    if request.method == 'POST':
        # CHANGES: Pass 'request=request' to the form for category choices
        form = TransactionForm(request.POST, instance=expense, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, 'Expense updated successfully!')
            return redirect(reverse('add_expense')) # Redirect back to the add/list page
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form when rendering for GET request (initial display)
        form = TransactionForm(instance=expense, request=request)

    # CHANGES: Fetch user-defined expense categories for the dropdown
    all_expense_categories = Category.objects.filter(
        user=request.user,
        type='expense'
    ).order_by('name')
    return render(request, 'home/edit_expense.html', {
        'form': form, # CHANGES: Pass the form instance to the template
        'expense': expense, # Pass the expense object for context
        'all_expense_categories': all_expense_categories # CHANGES: Pass categories for dropdown
    })

@login_required
def delete_expense_view(request, expense_id):
    expense = get_object_or_404(
        Transaction,
        id=expense_id,
        user=request.user
    )

    if request.method != 'POST':
        return redirect('add_expense')

    expense.delete()

    messages.success(
        request,
        'Expense deleted successfully!'
    )

    return redirect('add_expense')

def edit_income_view(request, income_id):
    """
    Handles editing an existing income, integrated with user-defined categories.
    """
    income = get_object_or_404(Income, id=income_id, user=request.user)
    if request.method == 'POST':
        # CHANGES: Use IncomeForm and pass 'request=request'
        form = IncomeForm(request.POST, instance=income, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, 'Income updated successfully!')
            return redirect(reverse('add_income'))
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use IncomeForm and pass 'request=request'
        form = IncomeForm(instance=income, request=request)

    # CHANGES: Fetch user-defined income categories
    all_income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')
    return render(request, 'home/edit_income.html', {
        'form': form, # CHANGES: Pass the form
        'income': income,
        'all_income_categories': all_income_categories # CHANGES: Pass categories for dropdown
    })

@login_required
def delete_income_view(request, income_id):
    """
    Handles deleting an existing income.
    """
    income = get_object_or_404(Income, id=income_id, user=request.user)
    if request.method == 'POST':
        income.delete()
        messages.success(request, 'Income deleted successfully!')
    return redirect('add_income')

@login_required
def add_income_view(request):
    """
    Handles adding new income, integrating with user-defined categories.
    Includes filtering and charting based on category.
    """
    if request.method == 'POST':
        # CHANGES: Use IncomeForm and pass 'request=request'
        form = IncomeForm(request.POST, request=request)
        if form.is_valid():
            income = form.save(commit=False)
            income.user = request.user
            income.save()
            messages.success(request, 'Income added successfully!')
            base_url = reverse('add_income')
            # CHANGES: Preserve selected category for redirect
            query_string = urlencode({'selected_category_id': income.category.pk})
            return redirect(f"{base_url}?{query_string}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use IncomeForm and pass 'request=request'
        form = IncomeForm(request=request)

    selected_category_id = request.GET.get('selected_category_id', '')
    group_by = request.GET.get('group_by', 'monthly')

    incomes = Income.objects.filter(user=request.user).order_by('-date')

    if selected_category_id:
        try:
            # CHANGES: Filter incomes by selected category ID
            incomes = incomes.filter(category__id=selected_category_id)
        except ValueError:
            pass

    if group_by == 'weekly':
        incomes_grouped = incomes.annotate(period=TruncWeek('date'))
    elif group_by == 'yearly':
        incomes_grouped = incomes.annotate(period=TruncYear('date'))
    else:
        incomes_grouped = incomes.annotate(period=TruncMonth('date'))

    grouped_totals = (
        incomes_grouped
        .values('period')
        .annotate(total=Sum('amount'))
        .order_by('period')
    )

    labels = []
    values = []
    for item in grouped_totals:
        if group_by == 'weekly':
            labels.append(item['period'].strftime("Week %W, %Y"))
        elif group_by == 'monthly':
            labels.append(item['period'].strftime("%B %Y"))
        elif group_by == 'yearly':
            labels.append(str(item['period'].year))
        values.append(float(item['total']))

    # CHANGES: Fetch user-defined income categories
    all_income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')

    return render(request, 'home/add_income.html', {
        'form': form, # CHANGES: Pass the form
        'incomes': incomes[:10],
        'category_labels': json.dumps(labels),
        'category_values': json.dumps(values),
        'all_income_categories': all_income_categories, # CHANGES: Pass categories for filtering dropdown
        'selected_category_id': selected_category_id,
        'group_by': group_by,
    })

@login_required
def view_all_transactions(request):
    """
    Displays the logged-in user's transactions with search,
    filtering, sorting, pagination, and summary statistics.
    """

    # Base queryset — always restricted to the authenticated user.
    transactions = (
        Transaction.objects
        .filter(user=request.user)
        .select_related('category')
    )

    # Search
    search_query = request.GET.get('q', '').strip()

    if search_query:
        transactions = transactions.filter(
            Q(description__icontains=search_query) |
            Q(category__name__icontains=search_query)
        )

    # Category filter
    category_id = request.GET.get('category', '').strip()

    if category_id:
        try:
            transactions = transactions.filter(category_id=int(category_id))
        except (TypeError, ValueError):
            category_id = ''

    # Date filters
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if date_from:
        transactions = transactions.filter(date__gte=date_from)

    if date_to:
        transactions = transactions.filter(date__lte=date_to)

    # Sorting
    sort = request.GET.get('sort', 'date_desc')

    sort_options = {
        'date_desc': '-date',
        'date_asc': 'date',
        'amount_desc': '-amount',
        'amount_asc': 'amount',
        'description': 'description',
    }

    order_by = sort_options.get(sort, '-date')

    transactions = transactions.order_by(order_by, '-created_at')

    # Summary statistics for the currently filtered dataset.
    filtered_count = transactions.count()

    filtered_total = (
        transactions.aggregate(total=Sum('amount'))['total']
        or Decimal('0.00')
    )

    # Pagination
    paginator = Paginator(transactions, 10)

    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # User-owned categories for the filter dropdown.
    categories = (
        Category.objects
        .filter(user=request.user, type='expense')
        .order_by('name')
    )

    return render(request, 'home/view_all_transactions.html', {
        'transactions': page_obj,
        'page_obj': page_obj,
        'paginator': paginator,
        'categories': categories,

        'search_query': search_query,
        'category_id': category_id,
        'date_from': date_from,
        'date_to': date_to,
        'sort': sort,

        'filtered_count': filtered_count,
        'filtered_total': filtered_total,
    })

@login_required
def create_budget_view(request):
    """
    Handles creating new budgets, integrated with user-defined categories.
    Includes charting of budget limits by category.
    """
    if request.method == 'POST':
        # CHANGES: Use BudgetForm and pass 'request=request'
        form = BudgetForm(request.POST, request=request)
        if form.is_valid():
            budget = form.save(commit=False)
            budget.user = request.user
            budget.save()
            messages.success(request, 'Budget created successfully!')
            base_url = reverse('create_budget')
            # CHANGES: Preserve selected category for redirect
            query_string = urlencode({'selected_category_id': budget.category.pk})
            return redirect(f"{base_url}?{query_string}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use BudgetForm and pass 'request=request'
        form = BudgetForm(request=request)

    selected_category_id = request.GET.get('selected_category_id', '')
    budgets = Budget.objects.filter(user=request.user)

    filtered_budgets_for_chart = budgets
    if selected_category_id:
        try:
            # CHANGES: Filter budgets by selected category ID
            filtered_budgets_for_chart = budgets.filter(category__id=selected_category_id)
        except ValueError:
            pass

    # CHANGES: Use category.name for chart labels
    budget_labels = [budget.category.name if budget.category else 'Uncategorized' for budget in filtered_budgets_for_chart]
    budget_values = [float(budget.limit) for budget in filtered_budgets_for_chart]

    # CHANGES: Fetch user-defined budget categories
    all_budget_categories = Category.objects.filter(user=request.user, type__in=['expense', 'budget']).order_by('name')

    return render(request, 'home/create_budget.html', {
        'form': form, # CHANGES: Pass the form
        'budgets': budgets, # All budgets (not just filtered for chart)
        'budget_labels': json.dumps(budget_labels),
        'budget_values': json.dumps(budget_values),
        'all_budget_categories': all_budget_categories, # CHANGES: Pass categories for filtering dropdown
        'selected_category_id': selected_category_id,
    })

@login_required
def edit_budget_view(request, budget_id):
    """
    Handles editing an existing budget, integrated with user-defined categories.
    """
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)

    if request.method == 'POST':
        # CHANGES: Use BudgetForm and pass 'request=request'
        form = BudgetForm(request.POST, instance=budget, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, 'Budget updated successfully!')
            return redirect('create_budget')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use BudgetForm and pass 'request=request'
        form = BudgetForm(instance=budget, request=request)

    # CHANGES: Fetch user-defined budget categories
    all_budget_categories = Category.objects.filter(user=request.user, type__in=['expense', 'budget']).order_by('name')

    return render(request, 'home/edit_budget.html', {
        'form': form, # CHANGES: Pass the form
        'budget': budget,
        'all_budget_categories': all_budget_categories # CHANGES: Pass categories for dropdown
    })

@login_required
def delete_budget_view(request, budget_id):
    """
    Handles deleting an existing budget.
    """
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    if request.method == 'POST':
        budget.delete()
        messages.success(request, 'Budget deleted successfully!')
    return redirect('create_budget')

@login_required
def set_goal_view(request):
    """
    Handles setting new goals, integrated with user-defined categories.
    Includes charting of goal targets by category.
    """
    if request.method == 'POST':
        # CHANGES: Use GoalForm and pass 'request=request'
        form = GoalForm(request.POST, request=request)
        if form.is_valid():
            goal = form.save(commit=False)
            goal.user = request.user
            goal.save()
            messages.success(request, 'Goal set successfully!')
            base_url = reverse('set_goal')
            # CHANGES: Preserve selected category for redirect
            query_string = urlencode({'selected_category_id': goal.category.pk})
            return redirect(f"{base_url}?{query_string}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use GoalForm and pass 'request=request'
        form = GoalForm(request=request)

    goals = Goal.objects.filter(user=request.user).order_by('-id')

    selected_category_id = request.GET.get('selected_category_id', '')
    filtered_goals_for_chart = goals
    if selected_category_id:
        try:
            # CHANGES: Filter goals by selected category ID
            filtered_goals_for_chart = goals.filter(category__id=selected_category_id)
        except ValueError:
            pass

    # CHANGES: Use category.name for chart labels
    goal_labels = [goal.category.name if goal.category else 'Uncategorized' for goal in filtered_goals_for_chart]
    goal_values = [float(goal.target_amount) for goal in filtered_goals_for_chart]

    # CHANGES: Fetch user-defined goal categories
    all_goal_categories = Category.objects.filter(user=request.user, type__in=['goal', 'savings', 'investments']).order_by('name')

    context = {
        'form': form, # CHANGES: Pass the form
        'goals': goals,
        'goal_labels': json.dumps(goal_labels),
        'goal_values': json.dumps(goal_values),
        'all_goal_categories': all_goal_categories, # CHANGES: Pass categories for filtering dropdown
        'selected_category_id': selected_category_id,
    }
    return render(request, 'home/set_goal.html', context)

@login_required
def edit_goal(request, goal_id):
    """
    Handles editing an existing goal, integrated with user-defined categories.
    """
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if request.method == 'POST':
        # CHANGES: Use GoalForm and pass 'request=request'
        form = GoalForm(request.POST, instance=goal, request=request)
        if form.is_valid():
            form.save()
            messages.success(request, 'Goal updated successfully!')
            return redirect('set_goal')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Use GoalForm and pass 'request=request'
        form = GoalForm(instance=goal, request=request)

    # CHANGES: Fetch user-defined goal categories
    all_goal_categories = Category.objects.filter(user=request.user, type__in=['goal', 'savings', 'investments']).order_by('name')

    return render(request, 'home/edit_goal.html', {
        'form': form, # CHANGES: Pass the form
        'goal': goal,
        'all_goal_categories': all_goal_categories # CHANGES: Pass categories for dropdown
    })

@login_required
def delete_goal(request, goal_id):
    """
    Handles deleting an existing goal.
    """
    goal = get_object_or_404(Goal, id=goal_id, user=request.user)
    if request.method == 'POST':
        goal.delete()
        messages.success(request, 'Goal deleted successfully!')
        return redirect('set_goal')
    return render(request, 'home/confirm_delete.html', {'goal': goal}) # A generic confirm delete page

# --- STATIC/INFO PAGES (CORE LOGIC - UNCHANGED) ---

def about_view(request):
    return render(request, 'home/about.html')

def services_view(request):
    return render(request, 'home/services.html')

def contact_view(request):
    return render(request, 'home/contact.html')

@login_required
def logout_view(request):
    # Clear stale messages from previous pages before logging out.
    list(messages.get_messages(request))
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('login')
