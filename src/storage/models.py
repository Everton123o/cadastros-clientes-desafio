"""Modelos SQLAlchemy persistidos no MySQL."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Registro(Base):
    """Cópia do CSV de entrada + chaves normalizadas usadas no blocking."""
    __tablename__ = "registros"

    id_registro: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    sistema_origem: Mapped[str] = mapped_column(String(30))
    nome: Mapped[str] = mapped_column(String(200))
    cpf: Mapped[str | None] = mapped_column(String(20))
    data_nascimento: Mapped[str | None] = mapped_column(String(20))
    telefone: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(String(200))
    cidade: Mapped[str | None] = mapped_column(String(100))
    uf: Mapped[str | None] = mapped_column(String(2))
    n_nome: Mapped[str | None] = mapped_column(String(200))
    n_cpf: Mapped[str | None] = mapped_column(String(14), index=True)
    n_cpf_valido: Mapped[bool] = mapped_column(Boolean, default=False)
    n_nascimento: Mapped[str | None] = mapped_column(String(10))
    n_fone8: Mapped[str | None] = mapped_column(String(8), index=True)
    n_email: Mapped[str | None] = mapped_column(String(200), index=True)


class Execucao(Base):
    """Uma rodada do pipeline: pesos, limiar e estatísticas ficam registrados."""
    __tablename__ = "execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    limiar_pontos: Mapped[float] = mapped_column(Float)
    pesos: Mapped[dict] = mapped_column(JSON)
    estatisticas: Mapped[dict] = mapped_column(JSON)

    grupos: Mapped[list["Grupo"]] = relationship(back_populates="execucao", cascade="all, delete-orphan")


class ParCandidato(Base):
    __tablename__ = "pares_candidatos"
    __table_args__ = (UniqueConstraint("execucao_id", "id_a", "id_b"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucoes.id", ondelete="CASCADE"), index=True)
    id_a: Mapped[int] = mapped_column(ForeignKey("registros.id_registro"))
    id_b: Mapped[int] = mapped_column(ForeignKey("registros.id_registro"))
    blocos: Mapped[str] = mapped_column(String(100))
    pontos: Mapped[float] = mapped_column(Float, index=True)
    confianca: Mapped[float] = mapped_column(Float)
    detalhes: Mapped[dict] = mapped_column(JSON)


class Grupo(Base):
    """Grupo proposto pelo pipeline. O status será usado pela tela de revisão (fase 2)."""
    __tablename__ = "grupos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    execucao_id: Mapped[int] = mapped_column(ForeignKey("execucoes.id", ondelete="CASCADE"), index=True)
    tamanho: Mapped[int] = mapped_column(Integer)
    confianca_media: Mapped[float | None] = mapped_column(Float)
    confianca_min: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), default="pendente")

    execucao: Mapped[Execucao] = relationship(back_populates="grupos")
    membros: Mapped[list["GrupoMembro"]] = relationship(cascade="all, delete-orphan")


class GrupoMembro(Base):
    __tablename__ = "grupo_membros"

    grupo_id: Mapped[int] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True)
    id_registro: Mapped[int] = mapped_column(ForeignKey("registros.id_registro"), primary_key=True)


class GabaritoAmostra(Base):
    """Os 100 registros sorteados (estratificados) para marcação manual."""
    __tablename__ = "gabarito_amostra"

    id_registro: Mapped[int] = mapped_column(ForeignKey("registros.id_registro"), primary_key=True)
    estrato: Mapped[str] = mapped_column(String(30))
    vizinhanca: Mapped[int] = mapped_column(Integer, index=True)


class GabaritoRotulo(Base):
    """Marcação manual: registros com o mesmo `pessoa` são a mesma pessoa."""
    __tablename__ = "gabarito_rotulos"

    id_registro: Mapped[int] = mapped_column(ForeignKey("registros.id_registro"), primary_key=True)
    pessoa: Mapped[str] = mapped_column(String(50))
    marcado_por: Mapped[str] = mapped_column(String(100))
    marcado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
