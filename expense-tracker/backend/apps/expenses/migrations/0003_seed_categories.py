"""Seed the global expense category list (Splitwise-compatible names)."""
from django.db import migrations


CATEGORIES = [
    # name, slug, icon, sort, splitwise parent names (pipe-separated)
    ("Food & Drink", "food-drink", "🍔", 10, "Food and drink|Dining out|Groceries"),
    ("Groceries", "groceries", "🛒", 20, "Groceries"),
    ("Shopping", "shopping", "🛍️", 30, "Shopping|Clothing|Electronics"),
    ("Transport", "transport", "🚗", 40, "Transportation|Car|Gas/fuel|Taxi|Parking"),
    ("Travel", "travel", "✈️", 50, "Travel|Hotel|Flights"),
    ("Entertainment", "entertainment", "🎬", 60, "Entertainment|Movies|Games|Music"),
    ("Utilities", "utilities", "💡", 70, "Utilities|Electricity|Water|Internet|Phone"),
    ("Rent & Home", "rent-home", "🏠", 80, "Home|Rent|Household supplies|Furniture"),
    ("Health", "health", "⚕️", 90, "Medical|Health"),
    ("Education", "education", "📚", 100, "Education"),
    ("Bills & Fees", "bills-fees", "🧾", 110, "Bills|Insurance|Taxes"),
    ("Other", "other", "📦", 900, "General|Other"),
]


def seed(apps, schema_editor):
    Category = apps.get_model("expenses", "Category")
    for name, slug, icon, sort, sw in CATEGORIES:
        Category.objects.update_or_create(
            slug=slug,
            defaults={"name": name, "icon": icon, "sort_order": sort, "splitwise_names": sw},
        )


def unseed(apps, schema_editor):
    Category = apps.get_model("expenses", "Category")
    Category.objects.filter(slug__in=[c[1] for c in CATEGORIES]).delete()


class Migration(migrations.Migration):
    dependencies = [("expenses", "0002_category_expense_category_coinaccrual")]
    operations = [migrations.RunPython(seed, unseed)]
