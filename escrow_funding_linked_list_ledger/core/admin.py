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

admin.site.register(Profile)
admin.site.register(Project)
admin.site.register(FundingStage)
admin.site.register(ProgressUpdate)
admin.site.register(ProgressVote)
admin.site.register(Block)
admin.site.register(Vote)