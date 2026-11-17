from django.contrib import admin

from laws.models import Article, Source


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("title", "citation", "short_label")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("label", "heading", "source", "path")
    list_filter = ("source",)
    search_fields = ("number", "heading", "text")
    list_select_related = ("source",)
