from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TextToSpeechModel(StrEnum):
    AURA_2_AMALTHEA_EN = "aura-2-amalthea-en"
    AURA_2_ANDROMEDA_EN = "aura-2-andromeda-en"
    AURA_2_APOLLO_EN = "aura-2-apollo-en"
    AURA_2_ARCAS_EN = "aura-2-arcas-en"
    AURA_2_ARIES_EN = "aura-2-aries-en"
    AURA_2_ASTERIA_EN = "aura-2-asteria-en"
    AURA_2_ATHENA_EN = "aura-2-athena-en"
    AURA_2_ATLAS_EN = "aura-2-atlas-en"
    AURA_2_AURORA_EN = "aura-2-aurora-en"
    AURA_2_CALLISTA_EN = "aura-2-callista-en"
    AURA_2_CORA_EN = "aura-2-cora-en"
    AURA_2_CORDELIA_EN = "aura-2-cordelia-en"
    AURA_2_DELIA_EN = "aura-2-delia-en"
    AURA_2_DRACO_EN = "aura-2-draco-en"
    AURA_2_ELECTRA_EN = "aura-2-electra-en"
    AURA_2_HARMONIA_EN = "aura-2-harmonia-en"
    AURA_2_HELENA_EN = "aura-2-helena-en"
    AURA_2_HERA_EN = "aura-2-hera-en"
    AURA_2_HERMES_EN = "aura-2-hermes-en"
    AURA_2_HYPERION_EN = "aura-2-hyperion-en"
    AURA_2_IRIS_EN = "aura-2-iris-en"
    AURA_2_JANUS_EN = "aura-2-janus-en"
    AURA_2_JUNO_EN = "aura-2-juno-en"
    AURA_2_JUPITER_EN = "aura-2-jupiter-en"
    AURA_2_LUNA_EN = "aura-2-luna-en"
    AURA_2_MARS_EN = "aura-2-mars-en"
    AURA_2_MINERVA_EN = "aura-2-minerva-en"
    AURA_2_NEPTUNE_EN = "aura-2-neptune-en"
    AURA_2_ODYSSEUS_EN = "aura-2-odysseus-en"
    AURA_2_OPHELIA_EN = "aura-2-ophelia-en"
    AURA_2_ORION_EN = "aura-2-orion-en"
    AURA_2_ORPHEUS_EN = "aura-2-orpheus-en"
    AURA_2_PANDORA_EN = "aura-2-pandora-en"
    AURA_2_PHOEBE_EN = "aura-2-phoebe-en"
    AURA_2_PLUTO_EN = "aura-2-pluto-en"
    AURA_2_SATURN_EN = "aura-2-saturn-en"
    AURA_2_SELENE_EN = "aura-2-selene-en"
    AURA_2_THALIA_EN = "aura-2-thalia-en"
    AURA_2_THEIA_EN = "aura-2-theia-en"
    AURA_2_VESTA_EN = "aura-2-vesta-en"
    AURA_2_ZEUS_EN = "aura-2-zeus-en"
    AURA_2_ALVARO_ES = "aura-2-alvaro-es"
    AURA_2_AQUILA_ES = "aura-2-aquila-es"
    AURA_2_CARINA_ES = "aura-2-carina-es"
    AURA_2_CELESTE_ES = "aura-2-celeste-es"
    AURA_2_DIANA_ES = "aura-2-diana-es"
    AURA_2_ESTRELLA_ES = "aura-2-estrella-es"
    AURA_2_JAVIER_ES = "aura-2-javier-es"
    AURA_2_NESTOR_ES = "aura-2-nestor-es"
    AURA_2_SELENA_ES = "aura-2-selena-es"
    AURA_2_SIRIO_ES = "aura-2-sirio-es"


# Deepgram's WebSocket endpoint serves raw frames only; mp3, opus, flac and aac
# are available over the REST endpoint, which this adapter does not cover.
class AudioEncoding(StrEnum):
    LINEAR16 = "linear16"
    MULAW = "mulaw"
    ALAW = "alaw"


class TextToSpeechConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: TextToSpeechModel | str = TextToSpeechModel.AURA_2_THALIA_EN
    encoding: AudioEncoding = AudioEncoding.LINEAR16
    sample_rate: int | None = Field(default=24000, gt=0)
