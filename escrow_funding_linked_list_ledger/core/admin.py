from django.contrib import admin

from .models import (
    Block,
    FundingStage,
    Profile,
    ProgressUpdate,
    ProgressVote,
    Project,
    Vote,
)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = (
        "project",
        "block_number",
        "transaction_type",
        "amount",
        "sender",
        "created_at",
    )
    readonly_fields = (
        "project",
        "stage",
        "progress_update",
        "block_number",
        "sender",
        "amount",
        "transaction_type",
        "previous_hash",
        "current_hash",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Profile)
admin.site.register(Project)
admin.site.register(FundingStage)
admin.site.register(ProgressUpdate)
admin.site.register(ProgressVote)
admin.site.register(Vote)