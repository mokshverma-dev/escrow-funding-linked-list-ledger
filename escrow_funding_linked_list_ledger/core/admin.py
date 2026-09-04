from django.contrib import admin

from .models import Block, Profile, Project, Vote

admin.site.register(Profile)
admin.site.register(Project)
admin.site.register(Block)
admin.site.register(Vote)