from .models import FeatureFlag


def is_feature_enabled(key, default=False):
    flag_state = FeatureFlag.objects.filter(key=key).values_list("is_active", flat=True).first()
    if flag_state is None:
        return default
    return flag_state
