from decimal import Decimal
import json
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    CustomUser,
    Category,
    Transaction,
    Income,
    Budget,
    Goal,
    Profile,
)


class UserAndProfileTests(TestCase):

    def test_user_creation_creates_profile(self):
        user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_user_email_is_unique(self):
        CustomUser.objects.create_user(
            username="user1",
            email="same@example.com",
            password="TestPassword123",
        )

        with self.assertRaises(Exception):
            CustomUser.objects.create_user(
                username="user2",
                email="same@example.com",
                password="TestPassword123",
            )


class CategoryTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

    def test_category_creation(self):
        category = Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )

        self.assertEqual(category.name, "Food")
        self.assertEqual(category.type, "expense")
        self.assertEqual(str(category), "Food (expense)")

    def test_duplicate_category_for_same_user_and_type_is_not_allowed(self):
        Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )

        with self.assertRaises(Exception):
            Category.objects.create(
                user=self.user,
                name="Food",
                type="expense",
            )

    def test_same_category_name_can_exist_for_different_types(self):
        Category.objects.create(
            user=self.user,
            name="Savings",
            type="expense",
        )

        category = Category.objects.create(
            user=self.user,
            name="Savings",
            type="income",
        )

        self.assertEqual(category.type, "income")


class TransactionTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )

    def test_transaction_creation(self):
        transaction = Transaction.objects.create(
            user=self.user,
            description="Lunch",
            amount=Decimal("250.50"),
            category=self.category,
            date=timezone.now().date(),
        )

        self.assertEqual(transaction.amount, Decimal("250.50"))
        self.assertEqual(transaction.description, "Lunch")
        self.assertEqual(
            str(transaction),
            "Lunch - 250.50",
        )

    def test_transaction_belongs_to_user(self):
        transaction = Transaction.objects.create(
            user=self.user,
            description="Groceries",
            amount=Decimal("1000.00"),
            category=self.category,
            date=timezone.now().date(),
        )

        self.assertEqual(transaction.user, self.user)


class IncomeTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Salary",
            type="income",
        )

    def test_income_creation(self):
        income = Income.objects.create(
            user=self.user,
            description="Monthly Salary",
            amount=Decimal("50000.00"),
            category=self.category,
            date=timezone.now().date(),
        )

        self.assertEqual(income.amount, Decimal("50000.00"))
        self.assertEqual(
            str(income),
            "Monthly Salary - 50000.00",
        )


class BudgetTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Food",
            type="budget",
        )

    def test_budget_creation(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            limit=Decimal("10000.00"),
        )

        self.assertEqual(budget.limit, Decimal("10000.00"))
        self.assertEqual(
            str(budget),
            "Food: 10000.00",
        )

    def test_duplicate_budget_for_same_category_and_date_is_not_allowed(self):
        budget_date = timezone.now().date()

        Budget.objects.create(
            user=self.user,
            category=self.category,
            limit=Decimal("10000.00"),
            date=budget_date,
        )

        with self.assertRaises(Exception):
            Budget.objects.create(
                user=self.user,
                category=self.category,
                limit=Decimal("12000.00"),
                date=budget_date,
            )


class GoalTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Travel",
            type="goal",
        )

    def test_goal_creation(self):
        goal = Goal.objects.create(
            user=self.user,
            description="Europe Trip",
            target_amount=Decimal("100000.00"),
            current_amount=Decimal("25000.00"),
            category=self.category,
        )

        self.assertEqual(goal.target_amount, Decimal("100000.00"))
        self.assertEqual(goal.current_amount, Decimal("25000.00"))
        self.assertEqual(str(goal), "Europe Trip")

    def test_goal_default_current_amount(self):
        goal = Goal.objects.create(
            user=self.user,
            description="New Laptop",
            target_amount=Decimal("100000.00"),
            category=self.category,
        )

        self.assertEqual(
            goal.current_amount,
            Decimal("0.00"),
        )
class ViewPageTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="viewuser",
            email="view@example.com",
            password="TestPassword123",
        )

        self.client.login(
            username="viewuser",
            password="TestPassword123",
        )

    def test_dashboard_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)

    def test_profile_page_loads(self):
        response = self.client.get(reverse("view_profile"))
        self.assertEqual(response.status_code, 200)

    def test_edit_profile_page_loads(self):
        response = self.client.get(reverse("edit_profile"))
        self.assertEqual(response.status_code, 200)

    def test_add_expense_page_loads(self):
        response = self.client.get(reverse("add_expense"))
        self.assertEqual(response.status_code, 200)

    def test_add_income_page_loads(self):
        response = self.client.get(reverse("add_income"))
        self.assertEqual(response.status_code, 200)

    def test_transactions_page_loads(self):
        response = self.client.get(reverse("view_all_transactions"))
        self.assertEqual(response.status_code, 200)

    def test_create_budget_page_loads(self):
        response = self.client.get(reverse("create_budget"))
        self.assertEqual(response.status_code, 200)

    def test_set_goal_page_loads(self):
        response = self.client.get(reverse("set_goal"))
        self.assertEqual(response.status_code, 200)

    def test_categories_page_loads(self):
        response = self.client.get(reverse("list_categories"))
        self.assertEqual(response.status_code, 200)

    def test_add_category_page_loads(self):
        response = self.client.get(reverse("add_category"))
        self.assertEqual(response.status_code, 200)

class CategoryCRUDTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="cruduser",
            email="crud@example.com",
            password="TestPassword123",
        )

        self.client.login(
            username="cruduser",
            password="TestPassword123",
        )

    def test_add_category(self):
        response = self.client.post(
            reverse("add_category"),
            {
                "name": "Entertainment",
                "type": "expense",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            Category.objects.filter(
                user=self.user,
                name="Entertainment",
                type="expense",
            ).exists()
        )

    def test_edit_category(self):
        category = Category.objects.create(
            user=self.user,
            name="Old Name",
            type="expense",
        )

        response = self.client.post(
            reverse("edit_category", args=[category.id]),
            {
                "name": "New Name",
                "type": "expense",
            },
        )

        self.assertEqual(response.status_code, 302)

        category.refresh_from_db()

        self.assertEqual(category.name, "New Name")
        self.assertEqual(category.type, "expense")

    def test_delete_category(self):
        category = Category.objects.create(
            user=self.user,
            name="To Delete",
            type="expense",
        )

        response = self.client.post(
            reverse("delete_category", args=[category.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Category.objects.filter(id=category.id).exists()
        )
class ExpenseCRUDTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="expenseuser",
            email="expense@example.com",
            password="TestPassword123",
        )

        self.other_user = CustomUser.objects.create_user(
            username="otheruser",
            email="other@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Food",
            type="expense",
        )

        self.client.login(
            username="expenseuser",
            password="TestPassword123",
        )

    def test_add_expense(self):
        response = self.client.post(
            reverse("add_expense"),
            {
                "description": "Lunch",
                "amount": "250.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            Transaction.objects.filter(
                user=self.user,
                description="Lunch",
                amount="250.00",
                category=self.category,
            ).exists()
        )

    def test_edit_expense(self):
        expense = Transaction.objects.create(
            user=self.user,
            description="Old Expense",
            amount="100.00",
            category=self.category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_expense", args=[expense.id]),
            {
                "description": "Updated Expense",
                "amount": "150.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        expense.refresh_from_db()

        self.assertEqual(expense.description, "Updated Expense")
        self.assertEqual(expense.amount, Decimal("150.00"))

    def test_delete_expense(self):
        expense = Transaction.objects.create(
            user=self.user,
            description="To Delete",
            amount="200.00",
            category=self.category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("delete_expense", args=[expense.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Transaction.objects.filter(id=expense.id).exists()
        )

    def test_cannot_edit_another_users_expense(self):
        other_category = Category.objects.create(
            user=self.other_user,
            name="Other Food",
            type="expense",
        )

        expense = Transaction.objects.create(
            user=self.other_user,
            description="Other User Expense",
            amount="500.00",
            category=other_category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_expense", args=[expense.id]),
            {
                "description": "Hacked Expense",
                "amount": "1.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 404)

        expense.refresh_from_db()

        self.assertEqual(expense.description, "Other User Expense")
        self.assertEqual(expense.amount, Decimal("500.00"))

class IncomeCRUDTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="incomeuser",
            email="income@example.com",
            password="TestPassword123",
        )

        self.other_user = CustomUser.objects.create_user(
            username="otherincome",
            email="otherincome@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Salary",
            type="income",
        )

        self.client.login(
            username="incomeuser",
            password="TestPassword123",
        )

    def test_add_income(self):
        response = self.client.post(
            reverse("add_income"),
            {
                "description": "Monthly Salary",
                "amount": "50000.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            Income.objects.filter(
                user=self.user,
                description="Monthly Salary",
                amount=Decimal("50000.00"),
                category=self.category,
            ).exists()
        )

    def test_edit_income(self):
        income = Income.objects.create(
            user=self.user,
            description="Old Income",
            amount="30000.00",
            category=self.category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_income", args=[income.id]),
            {
                "description": "Updated Income",
                "amount": "35000.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        income.refresh_from_db()

        self.assertEqual(income.description, "Updated Income")
        self.assertEqual(income.amount, Decimal("35000.00"))

    def test_delete_income(self):
        income = Income.objects.create(
            user=self.user,
            description="To Delete",
            amount="20000.00",
            category=self.category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("delete_income", args=[income.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Income.objects.filter(id=income.id).exists()
        )

    def test_cannot_edit_another_users_income(self):
        other_category = Category.objects.create(
            user=self.other_user,
            name="Other Salary",
            type="income",
        )

        income = Income.objects.create(
            user=self.other_user,
            description="Other User Income",
            amount="60000.00",
            category=other_category,
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_income", args=[income.id]),
            {
                "description": "Hacked Income",
                "amount": "1.00",
                "category": self.category.id,
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 404)

        income.refresh_from_db()

        self.assertEqual(income.description, "Other User Income")
        self.assertEqual(income.amount, Decimal("60000.00"))

class BudgetCRUDTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="budgetuser",
            email="budget@example.com",
            password="TestPassword123",
        )

        self.other_user = CustomUser.objects.create_user(
            username="otherbudget",
            email="otherbudget@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Food Budget",
            type="budget",
        )

        self.client.login(
            username="budgetuser",
            password="TestPassword123",
        )

    def test_add_budget(self):
        response = self.client.post(
            reverse("create_budget"),
            {
                "category": self.category.id,
                "limit": "10000.00",
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            Budget.objects.filter(
                user=self.user,
                category=self.category,
                limit=Decimal("10000.00"),
            ).exists()
        )

    def test_edit_budget(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            limit="10000.00",
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_budget", args=[budget.id]),
            {
                "category": self.category.id,
                "limit": "15000.00",
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 302)

        budget.refresh_from_db()

        self.assertEqual(budget.limit, Decimal("15000.00"))

    def test_delete_budget(self):
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            limit="10000.00",
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("delete_budget", args=[budget.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Budget.objects.filter(id=budget.id).exists()
        )

    def test_cannot_edit_another_users_budget(self):
        other_category = Category.objects.create(
            user=self.other_user,
            name="Other Budget",
            type="budget",
        )

        budget = Budget.objects.create(
            user=self.other_user,
            category=other_category,
            limit="20000.00",
            date="2026-10-04",
        )

        response = self.client.post(
            reverse("edit_budget", args=[budget.id]),
            {
                "category": self.category.id,
                "limit": "1.00",
                "date": "2026-10-04",
            },
        )

        self.assertEqual(response.status_code, 404)

        budget.refresh_from_db()

        self.assertEqual(budget.limit, Decimal("20000.00"))


class GoalCRUDTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="goaluser",
            email="goal@example.com",
            password="TestPassword123",
        )

        self.other_user = CustomUser.objects.create_user(
            username="othergoal",
            email="othergoal@example.com",
            password="TestPassword123",
        )

        self.category = Category.objects.create(
            user=self.user,
            name="Travel Goal",
            type="goal",
        )

        self.client.login(
            username="goaluser",
            password="TestPassword123",
        )

    def test_add_goal(self):
        response = self.client.post(
            reverse("set_goal"),
            {
                "description": "Europe Trip",
                "target_amount": "100000.00",
                "deadline": "2027-06-30",
                "category": self.category.id,
            },
        )

        self.assertEqual(response.status_code, 302)

        self.assertTrue(
            Goal.objects.filter(
                user=self.user,
                description="Europe Trip",
                target_amount=Decimal("100000.00"),
                category=self.category,
            ).exists()
        )

    def test_edit_goal(self):
        goal = Goal.objects.create(
            user=self.user,
            description="Old Goal",
            target_amount="50000.00",
            deadline="2027-06-30",
            category=self.category,
        )

        response = self.client.post(
            reverse("edit_goal", args=[goal.id]),
            {
                "description": "Updated Goal",
                "target_amount": "75000.00",
                "deadline": "2027-12-31",
                "category": self.category.id,
                "current_amount": "10000.00",
            },
        )

        self.assertEqual(response.status_code, 302)

        goal.refresh_from_db()

        self.assertEqual(goal.description, "Updated Goal")
        self.assertEqual(goal.target_amount, Decimal("75000.00"))

    def test_delete_goal(self):
        goal = Goal.objects.create(
            user=self.user,
            description="To Delete",
            target_amount="50000.00",
            deadline="2027-06-30",
            category=self.category,
        )

        response = self.client.post(
            reverse("delete_goal", args=[goal.id])
        )

        self.assertEqual(response.status_code, 302)

        self.assertFalse(
            Goal.objects.filter(id=goal.id).exists()
        )

    def test_cannot_edit_another_users_goal(self):
        other_category = Category.objects.create(
            user=self.other_user,
            name="Other Goal",
            type="goal",
        )

        goal = Goal.objects.create(
            user=self.other_user,
            description="Other User Goal",
            target_amount="200000.00",
            deadline="2027-06-30",
            category=other_category,
        )

        response = self.client.post(
            reverse("edit_goal", args=[goal.id]),
            {
                "description": "Hacked Goal",
                "target_amount": "1.00",
                "deadline": "2027-12-31",
                "category": self.category.id,
                "current_amount": "0.00",
            },
        )

        self.assertEqual(response.status_code, 404)

        goal.refresh_from_db()

        self.assertEqual(goal.description, "Other User Goal")
        self.assertEqual(
            goal.target_amount,
            Decimal("200000.00"),
        )
class TaxationTests(TestCase):

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="taxuser",
            email="tax@example.com",
            password="TestPassword123",
        )

        self.client.login(
            username="taxuser",
            password="TestPassword123",
        )

    def test_annual_tax_estimate(self):
        response = self.client.post(
            reverse("calculate_taxation"),
            data=json.dumps({
                "calculation_type": "annual_estimate",
                "annual_salary": "1200000.00",
                "opted_old_regime": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertIn("current_fy", data)

        current_fy = data["current_fy"]

        self.assertIn("taxable_income", current_fy)
        self.assertIn("tax_percentage", current_fy)
        self.assertIn("total_tax_amount", current_fy)
        self.assertIn("in_hand_salary", current_fy)

    def test_period_tax_calculation(self):
        Income.objects.create(
            user=self.user,
            description="Salary",
            amount="100000.00",
            date="2026-05-01",
        )

        Transaction.objects.create(
            user=self.user,
            description="Expenses",
            amount="20000.00",
            date="2026-05-15",
        )

        response = self.client.post(
            reverse("calculate_taxation"),
            data=json.dumps({
                "calculation_type": "period",
                "start_date": "2026-05-01",
                "end_date": "2026-06-01",
                "opted_old_regime": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertIn("period_net_income", data)
        self.assertEqual(data["period_net_income"], 80000.0)

        self.assertIn("current_fy", data)
        self.assertIn("previous_fy", data)

    def test_invalid_calculation_type(self):
        response = self.client.post(
            reverse("calculate_taxation"),
            data=json.dumps({
                "calculation_type": "invalid_type",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertEqual(
            data["error"],
            "Invalid calculation type",
        )

    def test_period_less_than_one_month(self):
        response = self.client.post(
            reverse("calculate_taxation"),
            data=json.dumps({
                "calculation_type": "period",
                "start_date": "2026-05-01",
                "end_date": "2026-05-15",
                "opted_old_regime": False,
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertEqual(
            data["error"],
            "End date must be at least one month after the start date.",
        )