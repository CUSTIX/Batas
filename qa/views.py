from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

from core import throttle
from qa import services
from qa.forms import QuestionForm

EXAMPLES = [
    "How many days of service incentive leave do I get?",
    "Kailan dapat ibigay ang 13th month pay?",
    "Can my employer deduct from my salary?",
    "How long is probationary employment?",
    "What are the just causes for termination?",
    "How much is overtime pay?",
]


@require_GET
def ask(request):
    """Questions are GET requests, so an answer has a link people can share."""
    form = QuestionForm(request.GET or None)
    context = {"form": form, "examples": EXAMPLES, "result": None}
    if form.is_bound and form.is_valid():
        if not throttle.hit("ask", throttle.client_ip(request), settings.QUESTIONS_PER_HOUR):
            context["limited"] = True
            return render(request, "qa/ask.html", context, status=429)
        context["result"] = services.answer(form.cleaned_data["q"])
    return render(request, "qa/ask.html", context)


@require_GET
def about(request):
    return render(request, "qa/about.html")
