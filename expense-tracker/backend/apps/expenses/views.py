"""Expense + comment API."""
from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.expenses import services
from apps.expenses.models import Comment, Expense
from apps.expenses.serializers import (
    CategorySerializer,
    CommentSerializer,
    ExpenseSerializer,
    ExpenseWriteSerializer,
)
from apps.expenses.models import Category
from apps.groups.models import Group
from apps.groups.permissions import is_group_member
from rest_framework.permissions import IsAuthenticated
from rest_framework import mixins


class CategoryViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Read-only global category list for the expense form + analytics."""

    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated]
    queryset = Category.objects.all()
    pagination_class = None


def _member_group_ids(user):
    return Group.objects.filter(members__user=user, members__is_active=True).values_list(
        "id", flat=True
    )


class ExpenseViewSet(viewsets.ModelViewSet):
    """CRUD for expenses in groups the user belongs to.

    Filter a group's expenses with ``?group=<id>``.
    """

    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = (
            Expense.objects.filter(group_id__in=_member_group_ids(self.request.user))
            .select_related("card", "created_by")
            .prefetch_related("payers__member", "splits__member", "comments__author")
        )
        group_id = self.request.query_params.get("group")
        if group_id:
            qs = qs.filter(group_id=group_id)
        return qs

    def create(self, request, *args, **kwargs):
        write = ExpenseWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        data = write.validated_data
        group = get_object_or_404(Group, id=request.data.get("group"))
        if not is_group_member(request.user, group.id):
            self.permission_denied(request, message="Not a group member.")
        try:
            expense = services.create_expense(user=request.user, group=group, **data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(ExpenseSerializer(expense).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        expense = self.get_object()
        if not is_group_member(request.user, expense.group_id):
            self.permission_denied(request, message="Not a group member.")
        write = ExpenseWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)
        try:
            expense = services.update_expense(expense=expense, user=request.user, **write.validated_data)
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        return Response(ExpenseSerializer(expense).data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=["get", "post"])
    def comments(self, request, pk=None):
        expense = self.get_object()
        if request.method == "GET":
            return Response(CommentSerializer(expense.comments.all(), many=True).data)
        body = request.data.get("body", "").strip()
        if not body:
            return Response({"detail": "Comment body required."}, status=status.HTTP_400_BAD_REQUEST)
        comment = Comment.objects.create(expense=expense, author=request.user, body=body)
        return Response(CommentSerializer(comment).data, status=status.HTTP_201_CREATED)


class CommentViewSet(viewsets.ViewSet):
    """Delete a comment (author only)."""

    permission_classes = [IsAuthenticated]

    def destroy(self, request, pk=None):
        comment = get_object_or_404(Comment.objects.select_related("expense"), pk=pk)
        if not is_group_member(request.user, comment.expense.group_id):
            self.permission_denied(request, message="Not a group member.")
        if comment.author_id != request.user.id:
            self.permission_denied(request, message="Only the author can delete this comment.")
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
