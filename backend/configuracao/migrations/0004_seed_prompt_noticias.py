from django.db import migrations

PROMPT = (
    "Você é um analista de tecnologia. Escreva em português do Brasil e traduza a notícia "
    "quando ela estiver em outro idioma. Estruture em: contexto breve, análise, "
    "consequências práticas e limitações. Baseie-se apenas nas evidências fornecidas e "
    "indique o link da fonte."
)


def criar_prompt(apps, schema_editor):
    Configuracao = apps.get_model("configuracao", "Configuracao")
    VersaoConfiguracao = apps.get_model("configuracao", "VersaoConfiguracao")
    config, _ = Configuracao.objects.get_or_create(
        escopo="secao",
        secao="noticias",
        agente="",
        defaults={"chave": "secao-noticias", "descricao": "Prompt editorial da seção Notícias"},
    )
    if not config.versoes.exists():
        VersaoConfiguracao.objects.create(
            configuracao=config, numero=1, campos={"prompt": PROMPT}, ativa=True
        )


def remover_prompt(apps, schema_editor):
    Configuracao = apps.get_model("configuracao", "Configuracao")
    Configuracao.objects.filter(chave="secao-noticias").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("configuracao", "0003_delete_auditoriaadministrativa"),
    ]

    operations = [
        migrations.RunPython(criar_prompt, remover_prompt),
    ]
