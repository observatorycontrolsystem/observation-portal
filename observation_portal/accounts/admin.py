from django.contrib import admin
from observation_portal.accounts.models import Profile
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as AuthUserAdmin
from django.contrib.admin.models import LogEntry


class LogEntryAdmin(admin.ModelAdmin):
    actions = None

    def get_list_display(self, request):
        return list(set(
            [field.name for field in self.opts.local_many_to_many] +
            [field.name for field in self.opts.local_fields]
        ))

    def get_readonly_fields(self, request, obj=None):
        return list(set(
            [field.name for field in self.opts.local_fields] +
            [field.name for field in self.opts.local_many_to_many]
        ))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class UserProfileInline(admin.StackedInline):
    model = Profile
    max_num = 1
    can_delete = False


class UserAdmin(AuthUserAdmin):
    inlines = [UserProfileInline]


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
admin.site.register(LogEntry, LogEntryAdmin)
