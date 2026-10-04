from django.urls import path
from . import views

urlpatterns = [
    # Home page
    path('', views.home_view, name='home'),

    # Authentication
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    # Password reset
    path('reset_password/', views.reset_password_view, name='reset_password'),
    path('verify-reset-code/', views.verify_reset_code_view, name='verify_reset_code'),

    # Profile
    path('profile/', views.view_profile, name='view_profile'),
    path('profile/edit/', views.edit_profile_view, name='edit_profile'),
    # Category Management
    path('categories/', views.list_categories_view, name='list_categories'),
    path('categories/add/', views.add_category_view, name='add_category'),
    path('categories/edit/<int:category_id>/', views.edit_category_view, name='edit_category'),
    path('categories/delete/<int:category_id>/', views.delete_category_view, name='delete_category'),

    # Transactions
    path('add_expense/', views.add_expense_view, name='add_expense'),
    path('add_income/', views.add_income_view, name='add_income'),
    path('view_all_transactions/', views.view_all_transactions, name='view_all_transactions'),

    # Expense CRUD
    path('edit_expense/<int:expense_id>/', views.edit_expense_view, name='edit_expense'),
    path('delete_expense/<int:expense_id>/', views.delete_expense_view, name='delete_expense'),

    # Income CRUD
    path('edit_income/<int:income_id>/', views.edit_income_view, name='edit_income'),
    path('delete_income/<int:income_id>/', views.delete_income_view, name='delete_income'),

    # Budget CRUD
    path('create_budget/', views.create_budget_view, name='create_budget'),
    path('edit_budget/<int:budget_id>/', views.edit_budget_view, name='edit_budget'),
    path('delete_budget/<int:budget_id>/', views.delete_budget_view, name='delete_budget'),

    # Goals CRUD
    path('set_goal/', views.set_goal_view, name='set_goal'),
    path('edit_goal/<int:goal_id>/', views.edit_goal, name='edit_goal'),
    path('delete_goal/<int:goal_id>/', views.delete_goal, name='delete_goal'),

    # Taxation
    path('taxation/calculate/', views.calculate_taxation, name='calculate_taxation'),

    # Static pages
    path('about/', views.about_view, name='about'),
    path('services/', views.services_view, name='services'),
    path('contact/', views.contact_view, name='contact'),
]
