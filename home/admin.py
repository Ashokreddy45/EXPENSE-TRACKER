# --- 3. admin.py ---
# This file registers your models with the Django admin interface
# and customizes their display.

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Transaction, Income, Budget, Goal, Profile, Category # Import Category

# CustomUser Admin (No changes needed here for category integration)
class CustomUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email')}),
        ('Permissions', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups', 'email')
    search_fields = ('username', 'first_name', 'last_name', 'email')

admin.site.register(CustomUser, CustomUserAdmin)

# New Category Admin
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'user')
    list_filter = ('type', 'user')
    search_fields = ('name', 'user__username')
    ordering = ('type', 'name')

admin.site.register(Category, CategoryAdmin)

# Modified Transaction (Expense) Admin
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'description', 'amount', 'get_category_name', 'date') # Use get_category_name
    list_filter = ('category__name', 'date', 'user') # Filter by category name
    search_fields = ('description', 'category__name') # Search by category name
    date_hierarchy = 'date'

    def get_category_name(self, obj):
        return obj.category.name if obj.category else 'N/A' # Handle null category
    get_category_name.admin_order_field = 'category__name' # Allow sorting by category name
    get_category_name.short_description = 'Category' # Display column header

admin.site.register(Transaction, TransactionAdmin)

# Modified Income Admin
class IncomeAdmin(admin.ModelAdmin):
    list_display = ('user', 'description', 'amount', 'get_category_name', 'date') # Use get_category_name
    list_filter = ('category__name', 'date', 'user') # Filter by category name
    search_fields = ('description', 'category__name') # Search by category name
    date_hierarchy = 'date'

    def get_category_name(self, obj):
        return obj.category.name if obj.category else 'N/A'
    get_category_name.admin_order_field = 'category__name'
    get_category_name.short_description = 'Category'

admin.site.register(Income, IncomeAdmin)

# Modified Budget Admin
class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_category_name', 'limit', 'date') # Use get_category_name
    list_filter = ('category__name', 'date', 'user') # Filter by category name
    search_fields = ('category__name',) # Search by category name
    date_hierarchy = 'date'

    def get_category_name(self, obj):
        return obj.category.name if obj.category else 'N/A'
    get_category_name.admin_order_field = 'category__name'
    get_category_name.short_description = 'Category'

admin.site.register(Budget, BudgetAdmin)

# Modified Goal Admin
class GoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'description', 'target_amount', 'deadline', 'get_category_name') # Use get_category_name
    list_filter = ('category__name', 'deadline', 'user') # Filter by category name
    search_fields = ('description', 'category__name') # Search by category name
    date_hierarchy = 'deadline'

    def get_category_name(self, obj):
        return obj.category.name if obj.category else 'N/A'
    get_category_name.admin_order_field = 'category__name'
    get_category_name.short_description = 'Category'

admin.site.register(Goal, GoalAdmin)

# Profile Admin (No changes needed here for category integration)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'reset_code')
    search_fields = ('user__username', 'user__email')

admin.site.register(Profile, ProfileAdmin)