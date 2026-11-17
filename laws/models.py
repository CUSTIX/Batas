from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from pgvector.django import HnswIndex, VectorField

EMBEDDING_DIMENSIONS = 768  # keep in step with settings.EMBEDDING_DIMENSIONS


class Source(models.Model):
    """One law: the Labor Code, PD 851 (13th month pay), ..."""

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200)
    citation = models.CharField(max_length=200)  # "Presidential Decree No. 442, as amended"
    short_label = models.CharField(max_length=20)  # how answers cite it: "Art." or "PD 851 Sec."
    url = models.URLField()

    def __str__(self):
        return self.title


class Article(models.Model):
    """One article or section of a law, as published."""

    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="articles")
    number = models.CharField(max_length=12)  # "95", "82-A", "1"
    sort_key = models.PositiveIntegerField(db_index=True)
    heading = models.CharField(max_length=300)  # "Right to service incentive leave"
    path = models.CharField(max_length=500, blank=True)  # "Book Three > Title I > Chapter III"
    text = models.TextField()

    class Meta:
        ordering = ["source", "sort_key", "number"]
        constraints = [
            models.UniqueConstraint(fields=["source", "number"], name="unique_article_per_source")
        ]

    def __str__(self):
        return f"{self.label}. {self.heading}"

    @property
    def label(self) -> str:
        """The citation answers use, e.g. "Art. 95" or "PD 851 Sec. 1"."""
        return f"{self.source.short_label} {self.number}"


class Passage(models.Model):
    """A retrievable piece of an article (long articles are split; short ones are one passage)."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="passages")
    ordinal = models.PositiveSmallIntegerField()
    text = models.TextField()
    search = SearchVectorField(null=True)
    embedding = VectorField(dimensions=EMBEDDING_DIMENSIONS, null=True, blank=True)

    class Meta:
        ordering = ["article", "ordinal"]
        constraints = [
            models.UniqueConstraint(fields=["article", "ordinal"], name="unique_passage_ordinal")
        ]
        indexes = [
            GinIndex(fields=["search"], name="passage_search_gin"),
            HnswIndex(
                name="passage_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
        ]

    def __str__(self):
        return f"{self.article.label} #{self.ordinal}"
