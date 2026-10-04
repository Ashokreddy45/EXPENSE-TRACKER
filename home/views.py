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
from django.db.models import Sum, Avg, Max
from django.db.models.functions import TruncWeek, TruncMonth, TruncYear
from django.utils import timezone
from django.utils.http import urlencode
from django.core.mail import send_mail

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
    Calculate estimated income tax and return the values
    required by calculate_taxation().
    """

    gross_income = Decimal(str(gross_income))

    if gross_income < Decimal("0"):
        gross_income = Decimal("0")

    # Standard deduction
    if is_salaried:
        if opted_old_regime:
            standard_deduction = Decimal("50000.00")
        else:
            standard_deduction = Decimal("75000.00")
    else:
        standard_deduction = Decimal("0.00")

    taxable_income = max(
        Decimal("0.00"),
        gross_income - standard_deduction,
    )

    # New tax regime
    if not opted_old_regime:
        slabs = [
            (Decimal("400000"), Decimal("0.00")),
            (Decimal("400000"), Decimal("0.05")),
            (Decimal("400000"), Decimal("0.10")),
            (Decimal("400000"), Decimal("0.15")),
            (Decimal("400000"), Decimal("0.20")),
            (None, Decimal("0.30")),
        ]

    # Old tax regime
    else:
        slabs = [
            (Decimal("250000"), Decimal("0.00")),
            (Decimal("250000"), Decimal("0.05")),
            (Decimal("500000"), Decimal("0.20")),
            (None, Decimal("0.30")),
        ]

    remaining_income = taxable_income
    total_tax = Decimal("0.00")

    for slab_limit, rate in slabs:
        if remaining_income <= Decimal("0.00"):
            break

        if slab_limit is None:
            slab_income = remaining_income
        else:
            slab_income = min(
                remaining_income,
                slab_limit,
            )

        total_tax += slab_income * rate
        remaining_income -= slab_income

    # 4% Health and Education Cess
    total_tax += total_tax * Decimal("0.04")

    # New-regime rebate
    if (
        not opted_old_regime
        and taxable_income <= Decimal("1200000")
    ):
        total_tax = Decimal("0.00")

    total_tax = total_tax.quantize(Decimal("0.01"))

    if taxable_income > Decimal("0.00"):
        tax_percentage = (
            total_tax / taxable_income
        ) * Decimal("100")
    else:
        tax_percentage = Decimal("0.00")

    return {
        "taxable_income_after_deduction": taxable_income,
        "tax_percentage": tax_percentage.quantize(
            Decimal("0.01")
        ),
        "total_tax_amount": total_tax,
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
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            calculation_type = data.get('calculation_type')
            user = request.user

            if calculation_type == 'annual_estimate':
                annual_salary_gross = Decimal(str(data.get('annual_salary', '0.00')))
                opted_old_regime = data.get('opted_old_regime', False)

                today = timezone.now().date()
                fy_start_year = today.year if today.month >= 4 else today.year - 1
                current_fy_string = f"{fy_start_year}-{fy_start_year + 1}"

                annual_tax_results = calculate_tax(annual_salary_gross, current_fy_string,
                                                   is_salaried=True, opted_old_regime=opted_old_regime)
                in_hand_salary = annual_salary_gross - annual_tax_results['total_tax_amount']

                response_data = {
                    'current_fy': {
                        'taxable_income': float(annual_tax_results['taxable_income_after_deduction']),
                        'tax_percentage': float(annual_tax_results['tax_percentage']),
                        'total_tax_amount': float(annual_tax_results['total_tax_amount']),
                        'in_hand_salary': float(in_hand_salary),
                    },
                }
                return JsonResponse(response_data)

            elif calculation_type == 'period':
                start_date_str = data.get('start_date')
                end_date_str = data.get('end_date')
                opted_old_regime = data.get('opted_old_regime', False)

                start_date = date.fromisoformat(start_date_str)
                end_date = date.fromisoformat(end_date_str)

                min_end_date = start_date + relativedelta(months=+1)
                if end_date < min_end_date:
                    return JsonResponse({'error': 'End date must be at least one month after the start date.'}, status=400)

                total_income_period = Income.objects.filter(
                    user=user,
                    date__gte=start_date,
                    date__lte=end_date
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                total_expense_period = Transaction.objects.filter(
                    user=user,
                    date__gte=start_date,
                    date__lte=end_date
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                period_net_income = total_income_period - total_expense_period

                fy_of_end_date_start_year = end_date.year if end_date.month >= 4 else end_date.year - 1
                current_fy_string = f"{fy_of_end_date_start_year}-{fy_of_end_date_start_year + 1}"
                current_fy_start, current_fy_end = get_financial_year_dates(str(fy_of_end_date_start_year))

                current_fy_total_income = Income.objects.filter(
                    user=user,
                    date__gte=current_fy_start,
                    date__lte=current_fy_end
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                current_fy_total_expense = Transaction.objects.filter(
                    user=user,
                    date__gte=current_fy_start,
                    date__lte=current_fy_end
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                current_fy_taxable_income_gross = current_fy_total_income - current_fy_total_expense
                current_fy_tax_results = calculate_tax(current_fy_taxable_income_gross, current_fy_string,
                                                       is_salaried=False, opted_old_regime=opted_old_regime)
                current_fy_in_hand_salary = current_fy_total_income - current_fy_tax_results['total_tax_amount']

                previous_fy_start_year = fy_of_end_date_start_year - 1
                previous_fy_string = f"{previous_fy_start_year}-{previous_fy_start_year + 1}"
                previous_fy_start, previous_fy_end = get_financial_year_dates(str(previous_fy_start_year))

                previous_fy_total_income = Income.objects.filter(
                    user=user,
                    date__gte=previous_fy_start,
                    date__lte=previous_fy_end
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                previous_fy_total_expense = Transaction.objects.filter(
                    user=user,
                    date__gte=previous_fy_start,
                    date__lte=previous_fy_end
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

                previous_fy_taxable_income_gross = previous_fy_total_income - previous_fy_total_expense
                previous_fy_tax_results = calculate_tax(previous_fy_taxable_income_gross, previous_fy_string,
                                                        is_salaried=False, opted_old_regime=opted_old_regime)
                previous_fy_in_hand_salary = previous_fy_total_income - previous_fy_tax_results['total_tax_amount']

                response_data = {
                    'period_net_income': float(period_net_income),
                    'current_fy': {
                        'taxable_income': float(current_fy_tax_results['taxable_income_after_deduction']),
                        'tax_percentage': float(current_fy_tax_results['tax_percentage']),
                        'total_tax_amount': float(current_fy_tax_results['total_tax_amount']),
                        'in_hand_salary': float(current_fy_in_hand_salary),
                    },
                    'previous_fy': {
                        'taxable_income': float(previous_fy_tax_results['taxable_income_after_deduction']),
                        'tax_percentage': float(previous_fy_tax_results['tax_percentage']),
                        'total_tax_amount': float(previous_fy_tax_results['total_tax_amount']),
                        'in_hand_salary': float(previous_fy_in_hand_salary),
                    },
                }
                return JsonResponse(response_data)
            else:
                return JsonResponse({'error': 'Invalid calculation type'}, status=400)

        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
        except ValueError as e:
            return JsonResponse({'error': f'Invalid input value or date format: {str(e)}'}, status=400)
        except Exception as e:
            logger.error("Unexpected error in calculate_taxation view: %s", e, exc_info=True)
            return JsonResponse({'error': f'An internal server error occurred: {str(e)}'}, status=500)
    return JsonResponse({'error': 'Invalid request method'}, status=405)


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
            category = form.save(commit=False)
            category.user = request.user # Assign the current user to the category
            category.save()
            messages.success(request, f"Category '{category.name}' added successfully!")
            return redirect('list_categories')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form when rendering for GET request
        form = CategoryForm(request=request)

    # Fetch categories for displaying in the template, categorized by type
    expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')
    income_categories = Category.objects.filter(user=request.user, type='income').order_by('name')
    budget_categories = Category.objects.filter(user=request.user, type__in=['expense', 'budget']).order_by('name') # Budgets typically use expense categories, or specific budget ones
    goal_categories = Category.objects.filter(user=request.user, type__in=['goal', 'savings', 'investments']).order_by('name') # Goals can have specific types

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
    budget_categories = Category.objects.filter(user=request.user, type__in=['expense', 'budget']).order_by('name')
    goal_categories = Category.objects.filter(user=request.user, type__in=['goal', 'savings', 'investments']).order_by('name')

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
        start_date = today - timedelta(days=7)
    elif time_period == 'yearly':
        start_date = today.replace(month=1, day=1)
    else: # monthly
        start_date = today.replace(day=1)

    if selected_type in ['income', 'expense']:
        queryset = queryset.filter(date__gte=start_date, date__lte=today)
    elif selected_type == 'goal':
        # Goals filter by deadline. If you want to show goals set within a period, change this.
        queryset = queryset.filter(deadline__gte=start_date) # No upper bound for 'to-do' goals

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
                .values('category__name') # CHANGES: Use category__name for grouping
                .annotate(total=Sum('target_amount'))
                .order_by('category__name') # CHANGES: Order by category__name
            )
            chart_labels = [entry['category__name'] if entry['category__name'] else 'Uncategorized' for entry in qs_chart]
            chart_data = [float(entry['total']) for entry in qs_chart]
        elif chart_type == 'overtime': # Optional: Goals over time (e.g., current amount vs target by deadline)
            # This would require more complex logic to show progress
            pass

    elif selected_type == 'budget':
        if chart_type == 'category':
            qs_chart = (
                queryset # Use the already filtered queryset for budget
                .values('category__name') # CHANGES: Use category__name for grouping
                .annotate(total=Sum('limit'))
                .order_by('category__name') # CHANGES: Order by category__name
            )
            chart_labels = [entry['category__name'] if entry['category__name'] else 'Uncategorized' for entry in qs_chart]
            chart_data = [float(entry['total']) for entry in qs_chart]
        elif chart_type == 'overtime': # Optional: Budgets over time (e.g., monthly budget limits)
            # This would require different Truncation for Budget models
            pass


    # Overall financial summaries (unchanged core logic)
    total_income_overall = Income.objects.filter(user=request.user).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_expenses_overall = Transaction.objects.filter(user=request.user).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')
    total_balance_overall = total_income_overall - total_expenses_overall

    monthly_spending = Transaction.objects.filter(
        user=request.user,
        date__year=today.year,
        date__month=today.month
    ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0.00')

    total_budget_limit = Budget.objects.filter(user=request.user).aggregate(Sum('limit'))['limit__sum'] or Decimal('0.00')
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
                profile.save()
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
        form = ResetCodeForm()
    return render(request, 'home/reset_password.html', {'form': form})

def verify_reset_code_view(request):
    if request.method == 'POST':
        form = ResetCodeForm(request.POST)
        if form.is_valid():
            reset_code = form.cleaned_data['reset_code']
            new_password = form.cleaned_data['new_password']
            try:
                profile = Profile.objects.get(reset_code=reset_code)
                user = profile.user
                user.set_password(new_password)
                user.save()
                profile.reset_code = ''
                profile.save()
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
    if request.method == 'POST':
        # CHANGES: Pass 'request=request' to the form to filter category choices
        form = TransactionForm(request.POST, request=request)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user # Assign the current user to the transaction
            transaction.save()
            messages.success(request, 'Expense added successfully!')
            base_url = reverse('add_expense')
            # CHANGES: Preserve selected category for redirect if needed (e.g., to keep filter active)
            query_string = urlencode({'selected_category_id': transaction.category.pk})
            return redirect(f"{base_url}?{query_string}")
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        # CHANGES: Pass 'request=request' to the form for GET request (initial display)
        form = TransactionForm(request=request)

    # Filtering and grouping logic for displaying expenses and charts
    selected_category_id = request.GET.get('selected_category_id', '')
    group_by = request.GET.get('group_by', 'monthly')

    expenses = Transaction.objects.filter(user=request.user).order_by('-date')

    if selected_category_id:
        try:
            # CHANGES: Filter transactions by the selected category ID
            expenses = expenses.filter(category__id=selected_category_id)
        except ValueError:
            pass # Handle invalid selected_category_id gracefully

    if group_by == 'weekly':
        expenses_grouped = expenses.annotate(period=TruncWeek('date'))
    elif group_by == 'yearly':
        expenses_grouped = expenses.annotate(period=TruncYear('date'))
    else: # Default to monthly
        expenses_grouped = expenses.annotate(period=TruncMonth('date'))

    grouped_totals = (
        expenses_grouped
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

    # CHANGES: Fetch user-defined expense categories for the dropdown filter
    all_expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')

    return render(request, 'home/add_expense.html', {
        'form': form, # CHANGES: Pass the form instance to the template
        'expenses': expenses[:5], # Display only a few recent ones
        'category_labels': json.dumps(labels), # Chart labels
        'category_values': json.dumps(values), # Chart data
        'all_expense_categories': all_expense_categories, # CHANGES: Pass categories for filtering dropdown
        'selected_category_id': selected_category_id, # Keep selected category in dropdown
        'group_by': group_by, # Keep selected grouping in dropdown
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
    all_expense_categories = Category.objects.filter(user=request.user, type='expense').order_by('name')
    return render(request, 'home/edit_expense.html', {
        'form': form, # CHANGES: Pass the form instance to the template
        'expense': expense, # Pass the expense object for context
        'all_expense_categories': all_expense_categories # CHANGES: Pass categories for dropdown
    })

@login_required
def delete_expense_view(request, expense_id):
    """
    Handles deleting an existing expense.
    """
    expense = get_object_or_404(Transaction, id=expense_id, user=request.user)
    if request.method == 'POST':
        expense.delete()
        messages.success(request, 'Expense deleted successfully!')
    return redirect('add_expense') # Redirect back to the add/list page

@login_required
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
    Displays all transactions for the logged-in user.
    """
    transactions = Transaction.objects.filter(user=request.user).order_by('-date')
    return render(request, 'home/view_all_transactions.html', {
        'transactions': transactions
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
    logout(request)
    messages.success(request, 'Logged out successfully!')
    return redirect('login')