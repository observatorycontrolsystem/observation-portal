from io import BytesIO
from os.path import basename

from django.dispatch import receiver
from django.db.models.signals import post_save, post_delete, pre_save
from django.core.files.base import ContentFile
from django.template.loader import render_to_string

from observation_portal.sciapplications.models import (
    ScienceApplicationUserReview,
    ScienceApplication,
    ScienceApplicationReview,
)

from PyPDF2 import PdfWriter
from xhtml2pdf import pisa


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


def _render_to_pdf(*args, **kwargs):
    """
    Like Django's render_to_string, but return a PDF byte string
    """
    html = render_to_string(*args, **kwargs)
    buf = BytesIO()
    r = pisa.CreatePDF(html, dest=buf)
    if r.err:
        raise Exception("failed to generate PDF")
    return buf


def _generate_cover_page_pdf(sci_app: ScienceApplication, show_authors: bool):
    instrument_allocations = [
      {"name": ", ".join(sorted(k)), **v} for k, v in sci_app.time_by_instrument_type().items()
    ]

    return _render_to_pdf(
      "sciapplications/cover_page.html",
      {
        "show_authors": show_authors,
        "id": sci_app.id,
        "title": sci_app.title,
        "abstract": sci_app.abstract,
        "pi": {
            "first_name": sci_app.pi_first_name,
            "last_name": sci_app.pi_last_name,
            "email": str(sci_app.pi),
        },
        "cois": sci_app.coinvestigator_set.all(),
        "instrument_allocations": instrument_allocations,
      }
    )

@receiver([pre_save], sender=ScienceApplicationReview)
def generate_review_pdf(sender, instance, **kwargs):
    """
    Generate a PDF for regular reviewers
    """
    sci_app: ScienceApplication = instance.science_application

    # only generate review PDFs for submitted applications to reduce load
    if sci_app.status != ScienceApplication.SUBMITTED:
        return

    # need a PDF to do anything
    if not sci_app.sci_justification_pdf:
        return

    # otherwise create a PDF version of the cover page and merge that with
    # the first PDF
    cover_page = _generate_cover_page_pdf(sci_app, show_authors=False)

    merged = PdfWriter()
    merged.append(cover_page)
    with sci_app.sci_justification_pdf.open(mode="rb") as fobj:
        merged.append(fobj)

    with BytesIO() as buff:
        merged.write(buff)
        instance.pdf = ContentFile(buff.getbuffer(), name=basename(sci_app.sci_justification_pdf.name))

@receiver([pre_save], sender=ScienceApplicationReview)
def generate_admin_review_pdf(sender, instance, **kwargs):
    """
    Generate a PDF for admin reviewers
    """
    sci_app: ScienceApplication = instance.science_application

    # only generate review PDFs for submitted applications to reduce load
    if sci_app.status != ScienceApplication.SUBMITTED:
        return

    # exit early if both PDFs are not set
    if not sci_app.sci_justification_pdf or not sci_app.references_pdf:
        return

    # otherwise create a PDF version of the cover page and merge that with
    # the first PDF and second PDF
    cover_page = _generate_cover_page_pdf(sci_app, show_authors=True)

    merged = PdfWriter()
    merged.append(cover_page)
    for f in [sci_app.sci_justification_pdf, sci_app.references_pdf]:
        with f.open(mode="rb") as fobj:
            merged.append(fobj)

    with BytesIO() as buff:
        merged.write(buff)
        instance.admin_pdf = ContentFile(buff.getbuffer(), name=basename(sci_app.sci_justification_pdf.name))
