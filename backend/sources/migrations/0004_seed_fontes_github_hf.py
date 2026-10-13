from django.db import migrations

FONTES = [
    {
        "nome": "GitHub (padrão)",
        "tipo": "github",
        "credencial_ref": "GITHUB_TOKEN",
        "parametros": {"janela_dias": 7, "min_estrelas": 100, "limite": 20, "selecao": 5},
    },
    {
        "nome": "Hugging Face (padrão)",
        "tipo": "huggingface",
        "credencial_ref": "HF_TOKEN",
        "parametros": {"limite": 30, "selecao": 5},
    },
]


def criar_fontes(apps, schema_editor):
    Fonte = apps.get_model("sources", "Fonte")
    for fonte in FONTES:
        Fonte.objects.get_or_create(
            tipo=fonte["tipo"],
            nome=fonte["nome"],
            defaults={
                "habilitada": True,
                "credencial_ref": fonte["credencial_ref"],
                "parametros": fonte["parametros"],
            },
        )


def remover_fontes(apps, schema_editor):
    Fonte = apps.get_model("sources", "Fonte")
    Fonte.objects.filter(nome__in=[f["nome"] for f in FONTES]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("sources", "0003_alter_fonte_tipo"),
    ]

    operations = [
        migrations.RunPython(criar_fontes, remover_fontes),
    ]
