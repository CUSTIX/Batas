from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from laws import selectors


@require_GET
def index(request):
    return render(request, "laws/index.html", {"sources": selectors.sources_with_articles()})


@require_GET
def article(request, source, number):
    found = selectors.article(source, number)
    if found is None:
        raise Http404("No such article.")
    return render(request, "laws/article.html", {"article": found})
