"""Expense serializers."""
from rest_framework import serializers

from apps.expenses.models import Category, Comment, Expense, ExpensePayer, ExpenseSplit


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon"]


class ExpensePayerSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.display_name", read_only=True)

    class Meta:
        model = ExpensePayer
        fields = ["member", "member_name", "amount_paid"]


class ExpenseSplitSerializer(serializers.ModelSerializer):
    member_name = serializers.CharField(source="member.display_name", read_only=True)

    class Meta:
        model = ExpenseSplit
        fields = ["member", "member_name", "share_amount", "split_type"]


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = Comment
        fields = ["id", "expense", "author", "author_name", "body", "created_at"]
        read_only_fields = ["author", "created_at"]

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.email
        return "Unknown"


class ExpenseSerializer(serializers.ModelSerializer):
    payers = ExpensePayerSerializer(many=True, read_only=True)
    splits = ExpenseSplitSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)
    card_name = serializers.CharField(source="card.display_name", read_only=True, default=None)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    category_icon = serializers.CharField(source="category.icon", read_only=True, default=None)
    comment_count = serializers.IntegerField(source="comments.count", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id", "group", "description", "category", "category_name", "category_icon",
            "currency", "total_amount", "fx_rate",
            "base_amount", "date", "merchant", "payment_mode", "card", "card_name",
            "cashback_program", "cashback_amount", "simplify_override",
            "created_by", "created_at", "payers", "splits", "comments", "comment_count",
        ]


class _LineSerializer(serializers.Serializer):
    member = serializers.IntegerField()
    amount_paid = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    share_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
    split_type = serializers.CharField(required=False, default="equal")


class ExpenseWriteSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=255)
    category_id = serializers.IntegerField(required=False, allow_null=True)
    currency = serializers.ChoiceField(choices=["INR", "USD", "EUR"])
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    date = serializers.DateField()
    merchant = serializers.CharField(required=False, allow_blank=True, default="")
    payment_mode = serializers.CharField(required=False, default="cash")
    card_id = serializers.IntegerField(required=False, allow_null=True)
    simplify_override = serializers.BooleanField(required=False, default=False)
    payers = _LineSerializer(many=True)
    splits = _LineSerializer(many=True)

    def validate(self, attrs):
        for p in attrs["payers"]:
            if p.get("amount_paid") is None:
                raise serializers.ValidationError("Each payer needs amount_paid.")
        for s in attrs["splits"]:
            if s.get("share_amount") is None:
                raise serializers.ValidationError("Each split needs share_amount.")
        return attrs
