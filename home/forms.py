# --- 2. forms.py ---
# This file defines your Django forms. New forms for Category management
# and modifications to existing forms to use ModelChoiceField for categories.

from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import get_user_model
from django.utils import timezone # Import timezone for clean_deadline in GoalForm

from .models import CustomUser, Transaction, Income, Budget, Goal, Profile, Category

User = get_user_model()

# Existing forms (no changes needed for these specific forms)
class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput,
        strip=False,
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput,
        strip=False,
    )

    class Meta:
        model = CustomUser
        fields = ["username", "email", "password"]

    def clean_username(self):
        username = self.cleaned_data.get("username")

        if CustomUser.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("This username is already taken.")

        return username

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "An account already exists with this email."
            )

        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")

        if password:
            candidate_user = CustomUser(
                username=self.cleaned_data.get("username", self.data.get("username", "")),
                email=self.cleaned_data.get("email", self.data.get("email", "")),
            )
            try:
                validate_password(password, user=candidate_user)
            except ValidationError as error:
                raise forms.ValidationError(error.messages)

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Passwords do not match.")

        return cleaned_data
class UserProfileEditForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This email address is already in use.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if CustomUser.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("This username is already taken.")
        return username

class UserLoginForm(AuthenticationForm):
    username = forms.CharField(max_length=254)
    password = forms.CharField(widget=forms.PasswordInput)

class ResetPasswordForm(forms.Form):
    email = forms.EmailField(label="Your Email", max_length=254)

class ResetCodeForm(forms.Form):
    reset_code = forms.CharField(max_length=100, label='Reset Code')
    new_password = forms.CharField(widget=forms.PasswordInput, label='New Password')
    confirm_password = forms.CharField(widget=forms.PasswordInput, label='Confirm Password')

    def clean(self):
        cleaned_data = super().clean()
        reset_code = cleaned_data.get('reset_code')
        new_password = cleaned_data.get('new_password')
        confirm_password = cleaned_data.get('confirm_password')

        if not reset_code:
            self.add_error('reset_code', 'Reset code is required.')
        if not new_password:
            self.add_error('new_password', 'New password is required.')
        if not confirm_password:
            self.add_error('confirm_password', 'Confirm password is required.')
        if new_password and confirm_password and new_password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')
        return cleaned_data

# New Category Form
class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type']
        widgets = {
            'type': forms.RadioSelect(choices=Category.CATEGORY_TYPES),
        }

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input rounded-md shadow-sm border-gray-300 focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'

    def clean_name(self):
        name = self.cleaned_data['name']
        category_type = self.cleaned_data.get('type')
        user = self.request.user if self.request else None
        if user and category_type:
            qs = Category.objects.filter(user=user, name__iexact=name, type=category_type)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"You already have an {category_type} category named '{name}'.")
        return name

# Modified Transaction Form
class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['description', 'amount', 'category', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'})
        }

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        empty_label="Select Category",
        label="Category"
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # SECURITY:
        # Only show expense categories belonging to the logged-in user.
        if self.request and self.request.user.is_authenticated:
            self.fields['category'].queryset = Category.objects.filter(
                user=self.request.user,
                type='expense'
            ).order_by('name')
        else:
            self.fields['category'].queryset = Category.objects.none()

        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = (
                'form-input rounded-md shadow-sm border-gray-300 '
                'focus:border-indigo-300 focus:ring '
                'focus:ring-indigo-200 focus:ring-opacity-50'
            )

    def clean_description(self):
        description = (self.cleaned_data.get('description') or '').strip()

        if not description:
            raise forms.ValidationError(
                "Expense description cannot be empty."
            )

        return description

    def clean_amount(self):
        amount = self.cleaned_data.get('amount')

        if amount is None:
            return amount

        if amount <= 0:
            raise forms.ValidationError(
                "Expense amount must be greater than 0."
            )

        return amount

    def clean_date(self):
        expense_date = self.cleaned_data.get('date')

        if expense_date is None:
            raise forms.ValidationError(
                "Expense date is required."
            )

        from django.utils import timezone

        today = timezone.localdate()

        if expense_date > today:
            raise forms.ValidationError(
                "Expense date cannot be in the future."
            )

        return expense_date

    def clean_category(self):
        category = self.cleaned_data.get('category')

        if category is None:
            raise forms.ValidationError(
                "Please select a valid expense category."
            )

        if not self.request or not self.request.user.is_authenticated:
            raise forms.ValidationError(
                "Authentication is required."
            )

        # Defense-in-depth:
        # Prevent manually submitted category IDs belonging to another user.
        if category.user_id != self.request.user.id:
            raise forms.ValidationError(
                "Invalid expense category."
            )

        if category.type != 'expense':
            raise forms.ValidationError(
                "Selected category is not an expense category."
            )

        return category
# Modified Income Form
class IncomeForm(forms.ModelForm):
    class Meta:
        model = Income
        fields = ['description', 'amount', 'category', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        empty_label="Select Category",
        label="Category"
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            self.fields['category'].queryset = Category.objects.filter(user=self.request.user, type='income').order_by('name')
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input rounded-md shadow-sm border-gray-300 focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'

# Modified Budget Form
class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ['category', 'limit', 'date']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
        }

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        empty_label="Select Category",
        label="Category"
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            self.fields['category'].queryset = Category.objects.filter(user=self.request.user, type__in=['expense', 'budget']).order_by('name')
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input rounded-md shadow-sm border-gray-300 focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        date = cleaned_data.get('date')
        user = self.request.user if self.request else None
        if category and date and user:
            qs = Budget.objects.filter(
                user=user,
                category=category,
                date__year=date.year,
                date__month=date.month
            )
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(f"You already have a budget for '{category.name}' for {date.strftime('%B %Y')}.")
        return cleaned_data

# Modified Goal Form
class GoalForm(forms.ModelForm):
    class Meta:
        model = Goal
        fields = ['description', 'target_amount', 'deadline', 'category']
        widgets = {
            'deadline': forms.DateInput(attrs={'type': 'date'}),
        }

    category = forms.ModelChoiceField(
        queryset=Category.objects.none(),
        empty_label="Select Category",
        label="Category"
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if self.request:
            self.fields['category'].queryset = Category.objects.filter(user=self.request.user, type__in=['goal', 'savings', 'investments']).order_by('name')
        for field_name, field in self.fields.items():
            field.widget.attrs['class'] = 'form-input rounded-md shadow-sm border-gray-300 focus:border-indigo-300 focus:ring focus:ring-indigo-200 focus:ring-opacity-50'

    def clean_deadline(self):
        deadline = self.cleaned_data.get('deadline')
        if deadline and deadline < timezone.now().date():
            raise forms.ValidationError("Deadline must be today or in the future.")
        return deadline