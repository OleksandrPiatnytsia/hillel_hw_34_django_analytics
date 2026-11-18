"""Model factories (factory-boy): test objects with valid data in one line.

UserFactory()                       a user with a unique username
UserFactory(username="ann")         any field can be given
"""

import factory

from users.models import User

# The password of every factory user, for the tests that log in with a form
PASSWORD = "test-password-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda number: f"user{number}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.com")
    password = PASSWORD

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # create_user() hashes the password, as a real sign-up would;
        # the default create() would store the plain text
        return model_class.objects.create_user(*args, **kwargs)
