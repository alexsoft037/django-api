from django.contrib.auth import forms as auth_forms, get_user_model


UserModel = get_user_model()


class PasswordResetForm(auth_forms.PasswordResetForm):
    def get_users(self, email):
        """Given an email, return matching user(s) who should receive a reset.

        This method does not filter out users with unusable password.
        """
        email_field = UserModel.get_email_field_name()
        active_users = UserModel._default_manager.filter(
            **{f"{email_field}__iexact": email, "is_active": True}
        )
        return active_users
