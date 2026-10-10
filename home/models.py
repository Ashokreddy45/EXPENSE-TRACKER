from django.db import models
from django.db.models import Q
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from django.contrib.auth.models import AbstractUser

# Custom User model
class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)

# New Category Model
class Category(models.Model):
    CATEGORY_TYPES = [
        ('expense', 'Expense'),
        ('income', 'Income'),
        ('budget', 'Budget'),
        ('goal', 'Goal'),
    ]

    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=CATEGORY_TYPES)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='categories')

    class Meta:
        unique_together = ('user', 'name', 'type')
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} ({self.type})"

# Modified Transaction Model
class Transaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='transactions')
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['user', '-date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name='transaction_amount_positive',
            ),
        ]

    def __str__(self):
        return f"{self.description} - {self.amount}"



class RegisteredCredential(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    credential_id = models.BinaryField()
    public_key = models.BinaryField()
    sign_count = models.IntegerField(default=0)

    def __str__(self):
        return f"Credential for {self.user.username}"


# Modified Income Model
class Income(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='incomes')
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='incomes')
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.description} - {self.amount}"

# Modified Budget Model
class Budget(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='budgets')
    limit = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'category', 'date')
        ordering = ['-date', 'category__name']

    def __str__(self):
        return f"{self.category.name}: {self.limit}"

# Modified Goal Model
class Goal(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='goals')
    description = models.CharField(max_length=255)
    target_amount = models.DecimalField(max_digits=10, decimal_places=2)
    deadline = models.DateField(null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='goals')
    current_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-deadline', 'category__name']

    def __str__(self):
        return self.description

# Profile model
class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    reset_code = models.CharField(max_length=6, blank=True, null=True)
    reset_code_created_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username

# Signal for Profile creation
# ---------------------------------------------------------
# DEFAULT USER CATEGORIES
# ---------------------------------------------------------

DEFAULT_CATEGORIES = {
    'expense': [
        'Food',
        'Groceries',
        'Dining Out',
        'Transport',
        'Fuel',
        'Rent',
        'Bills',
        'Utilities',
        'Shopping',
        'Entertainment',
        'Health',
        'Education',
        'Clothing',
        'Insurance',
        'Subscriptions',
        'Travel',
        'Gifts',
        'Personal Care',
        'Electronics',
        'Other Expense',
    ],
    'income': [
        'Salary',
        'Bonus',
        'Business',
        'Freelance',
        'Rental Income',
        'Interest',
        'Investment Returns',
        'Gift',
        'Other Income',
    ],
    'budget': [
        'Essentials',
        'Lifestyle',
        'Debt',
        'Debt Repayment',
        'Education',
        'Savings',
        'Investments',
        'Travel',
        'Other Budget',
    ],
    'goal': [
        'Emergency Fund',
        'New Laptop',
        'New Phone',
        'Vacation',
        'Car',
        'Education',
        'Home',
        'Retirement',
        'General Savings',
        'Other Goal',
    ],
}


def create_default_categories_for_user(user):
    for category_type, category_names in DEFAULT_CATEGORIES.items():
        for category_name in category_names:
            Category.objects.get_or_create(
                user=user,
                name=category_name,
                type=category_type,
            )


# Signal for Profile creation and default category provisioning
@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        create_default_categories_for_user(instance)
    else:
        if hasattr(instance, 'profile'):
            instance.profile.save()
