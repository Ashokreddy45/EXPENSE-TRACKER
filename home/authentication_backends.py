from django.contrib.auth.backends import BaseBackend
# Import get_user_model instead of User directly
from django.contrib.auth import get_user_model 

class EmailOrUsernameBackend(BaseBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        # Get the currently active user model (which will be home.CustomUser)
        UserModel = get_user_model() 
        try:
            # Determine if the username is an email or username
            if '@' in username and '.' in username:
                user = UserModel.objects.get(email=username)
            else:
                user = UserModel.objects.get(username=username)
            
            # Check the password
            if user.check_password(password):
                return user
        except UserModel.DoesNotExist: # Use UserModel.DoesNotExist
            return None

    def get_user(self, user_id):
        # Get the currently active user model
        UserModel = get_user_model() 
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist: # Use UserModel.DoesNotExist
            return None