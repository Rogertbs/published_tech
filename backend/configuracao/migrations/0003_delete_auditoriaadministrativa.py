from django.db import migrations


def copiar_auditoria(apps, schema_editor):
    Antiga = apps.get_model("configuracao", "AuditoriaAdministrativa")
    Nova = apps.get_model("auditoria", "AuditoriaAdministrativa")
    linhas = [
        Nova(
            usuario_id=item.usuario_id,
            acao=item.acao,
            entidade=item.entidade,
            entidade_id=item.entidade_id,
            antes=item.antes,
            depois=item.depois,
            criado_em=item.criado_em,
        )
        for item in Antiga.objects.all()
    ]
    Nova.objects.bulk_create(linhas)


def reverter(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("configuracao", "0002_auditoriaadministrativa"),
        ("auditoria", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(copiar_auditoria, reverter),
        migrations.DeleteModel(
            name="AuditoriaAdministrativa",
        ),
    ]
