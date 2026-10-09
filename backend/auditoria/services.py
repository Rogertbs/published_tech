def registrar(acao, entidade, entidade_id, *, usuario=None, antes=None, depois=None):
    from auditoria.models import AuditoriaAdministrativa

    return AuditoriaAdministrativa.objects.create(
        usuario=usuario,
        acao=acao,
        entidade=entidade,
        entidade_id=str(entidade_id),
        antes=antes,
        depois=depois,
    )
