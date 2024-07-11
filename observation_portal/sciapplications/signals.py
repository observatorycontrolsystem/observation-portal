from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete

from observation_portal.sciapplications.models import (
    ScienceApplicationUserReview,
)


@receiver([post_save, post_delete], sender=ScienceApplicationUserReview)
def update_review_mean(sender, instance, **kwargs):
    review = instance.science_application_review

    finished_user_reviews = ScienceApplicationUserReview.objects.filter(science_application_review=review, finished=True, grade__isnull=False)

    if len(finished_user_reviews) > 0:
        mean_grade = sum(x.grade for x in finished_user_reviews) / len(finished_user_reviews)
        review.mean_grade = mean_grade
    else:
        review.mean_grade = None

    review.save()
