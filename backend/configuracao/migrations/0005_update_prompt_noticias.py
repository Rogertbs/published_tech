from django.db import migrations

PROMPT = (
    "Você é um analista de tecnologia. Escreva em português do Brasil e traduza a notícia "
    "quando ela estiver em outro idioma. Comece com uma linha no formato "
    "'TÍTULO: <título curto em português>'. Depois estruture em: contexto breve, análise, "
    "consequências práticas e limitações. Baseie-se apenas nas evidências fornecidas e "
    "indique o link da fonte."
)


def atualizar_prompt(apps, schema_editor):
    Configuracao = apps.get_model("configuracao", "Configuracao")
    VersaoConfiguracao = apps.get_model("configuracao", "VersaoConfiguracao")
    config = Configuracao.objects.filter(chave="secao-noticias").first()
    if config is None:
        return
    if config.versoes.filter(campos__prompt=PROMPT).exists():
        return
    numero = (config.versoes.order_by("-numero").first().numero if config.versoes.exists() else 0) + 1
    config.versoes.update(ativa=False)
    VersaoConfiguracao.objects.create(
        configuracao=config, numero=numero, campos={"prompt": PROMPT}, ativa=True
    )


def reverter(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("configuracao", "0004_seed_prompt_noticias"),
    ]

    operations = [
        migrations.RunPython(atualizar_prompt, reverter),
    ]
