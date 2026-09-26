"""
Guardas do armazenamento e do backup (auditoria 2026-09-26).

Cada guarda tem o caso doente e o legítimo de mesmo sinal ao lado.
"""
import json
import os
import time

import pytest

from src.services import dbService
from utils import backup
from utils.storage import _file_lock, load_json_safe, p, save_json_safe


def _escreve(caminho, texto):
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


def test_corrompido_recupera_do_backup_de_emergencia():
    h = p("history.json")
    _escreve(h, '["https://a/1", "https://a/2"')
    _escreve(h + ".backup", json.dumps(["https://a/1", "https://a/2"]))
    assert load_json_safe(h, "PADRAO") == ["https://a/1", "https://a/2"]
    with open(h, encoding="utf-8") as f:
        assert json.load(f) == ["https://a/1", "https://a/2"]


def test_integro_nao_consulta_backup():
    h = p("history.json")
    _escreve(h, '["https://a/1"]')
    _escreve(h + ".backup", json.dumps(["https://OUTRO"]))
    assert load_json_safe(h, "PADRAO") == ["https://a/1"]


def test_corrompido_recupera_do_backup_automatico_mais_recente(dados_isolados):
    pasta = dados_isolados / "backups"
    pasta.mkdir()
    antigo = pasta / "history.json_20260101_000000_auto.json.backup"
    novo = pasta / "history.json_20260925_000000_auto.json.backup"
    _escreve(antigo, json.dumps(["velho"]))
    _escreve(novo, json.dumps(["novo"]))
    os.utime(antigo, (time.time() - 3600, time.time() - 3600))
    h = p("history.json")
    _escreve(h, "[corrompido")
    assert load_json_safe(h, "PADRAO") == ["novo"]


def test_corrompido_sem_backup_devolve_padrao():
    h = p("history.json")
    _escreve(h, "[corrompido")
    assert load_json_safe(h, "PADRAO") == "PADRAO"


def test_excecao_do_corpo_propaga_com_o_tipo_original(dados_isolados):
    alvo = str(dados_isolados / "x.json")
    with pytest.raises(ValueError, match="original"):
        with _file_lock(alvo):
            raise ValueError("original")
    assert not os.path.exists(alvo + ".lock")


def test_lock_de_outro_processo_nao_e_apagado(dados_isolados, monkeypatch):
    import utils.storage as st
    monkeypatch.setattr(st, "_LOCK_ESPERA_S", 0.1)
    alvo = str(dados_isolados / "y.json")
    _escreve(alvo + ".lock", "")
    with _file_lock(alvo):
        pass
    assert os.path.exists(alvo + ".lock")


def test_save_nao_deixa_temporario(dados_isolados):
    alvo = p("state.json")
    save_json_safe(alvo, {"a": 1})
    assert sorted(os.listdir(dados_isolados)) == ["state.json"]


def test_backup_de_arquivo_antigo_sobrevive_a_limpeza(dados_isolados):
    cfg = p("config.json")
    _escreve(cfg, "{}")
    velho = time.time() - 200 * 86400
    os.utime(cfg, (velho, velho))
    backup.auto_backup_critical_files()
    nomes = os.listdir(dados_isolados / "backups")
    assert any(n.startswith("config.json_") for n in nomes)


def test_backup_realmente_velho_e_removido_mas_o_mais_recente_fica(dados_isolados):
    pasta = backup.ensure_backup_dir()
    velho = pasta / "config.json_20250101_000000_auto.json.backup"
    recente = pasta / "config.json_20260925_000000_auto.json.backup"
    _escreve(velho, "{}")
    _escreve(recente, "{}")
    t = time.time() - 200 * 86400
    os.utime(velho, (t, t))
    os.utime(recente, (t + 10, t + 10))
    backup.cleanup_old_backups()
    assert not velho.exists()
    assert recente.exists()


def test_teto_de_backups_e_por_arquivo():
    pasta = backup.ensure_backup_dir()
    agora = time.time()
    for i in range(35):
        f = pasta / f"database.json_20260926_{i:06d}_auto.json.backup"
        _escreve(f, "{}")
        os.utime(f, (agora - i, agora - i))
    unico = pasta / "config.json_20260926_000000_auto.json.backup"
    _escreve(unico, "{}")
    os.utime(unico, (agora - 1000, agora - 1000))
    backup.cleanup_old_backups()
    nomes = os.listdir(pasta)
    assert sum(n.startswith("database.json_") for n in nomes) == backup.MAX_BACKUPS_PER_FILE
    assert unico.name in nomes


def test_backup_mora_no_data_dir_e_nao_no_cwd(dados_isolados, tmp_path, monkeypatch):
    outro_cwd = tmp_path / "outro"
    outro_cwd.mkdir()
    monkeypatch.chdir(outro_cwd)
    _escreve(p("state.json"), "{}")
    backup.auto_backup_critical_files()
    assert (dados_isolados / "backups").is_dir()
    assert not (outro_cwd / "data").exists()


def test_db_path_segue_data_dir_definido_depois_do_import(tmp_path, monkeypatch):
    novo = tmp_path / "novo"
    novo.mkdir()
    monkeypatch.setenv("DATA_DIR", str(novo))
    assert dbService.db_path() == str(novo / "database.json")
