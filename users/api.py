from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.views import TokenObtainPairView


class ThrottledTokenObtainPairView(TokenObtainPairView):
    """POST /api/token/: username + password -> access and refresh tokens.

    The same view as simplejwt's, with a low request limit ("token" in
    REST_FRAMEWORK DEFAULT_THROTTLE_RATES): every request checks a password,
    so without a limit it would be a free password-guessing machine.
    """

    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token"
