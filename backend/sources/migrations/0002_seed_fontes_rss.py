from django.db import migrations

FONTES = [
    {
        "nome": "TechCrunch",
        "feed_url": "https://techcrunch.com/feed/",
        "nome_fonte": "TechCrunch",
    },
    {
        "nome": "Ars Technica",
        "feed_url": "https://feeds.arstechnica.com/arstechnica/index",
        "nome_fonte": "Ars Technica",
    },
    {
        "nome": "The Register",
        "feed_url": "https://www.theregister.com/headlines.atom",
        "nome_fonte": "The Register",
    },
    {
        "nome": "InfoQ",
        "feed_url": "https://feed.infoq.com/",
        "nome_fonte": "InfoQ",
    },
]


def criar_fontes(apps, schema_editor):
    Fonte = apps.get_model("sources", "Fonte")
    for fonte in FONTES:
        Fonte.objects.get_or_create(
            tipo="rss",
            nome=fonte["nome"],
            defaults={
                "habilitada": True,
                "parametros": {
                    "feed_url": fonte["feed_url"],
                    "nome_fonte": fonte["nome_fonte"],
                    "limite": 10,
                    "selecao": 1,
                },
            },
        )


def remover_fontes(apps, schema_editor):
    Fonte = apps.get_model("sources", "Fonte")
    Fonte.objects.filter(tipo="rss", nome__in=[f["nome"] for f in FONTES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(criar_fontes, remover_fontes),
    ]
