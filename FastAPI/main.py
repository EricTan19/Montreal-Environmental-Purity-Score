from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Annotated, Any

import matplotlib
import numpy as np
import scipy.stats as stats
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

import models
from computer_use import (
    ComputerUseApprovalRequest,
    ComputerUseSessionResponse,
    ComputerUseStartRequest,
    computer_use_manager,
)
from database import SessionLocal, engine


matplotlib.use("Agg")
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
GRAPH_DIR = STATIC_DIR / "graphs"
GRAPH_DIR.mkdir(parents=True, exist_ok=True)


app = FastAPI(title="Montreal Environmental Purity Score API")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuestionnaireBase(BaseModel):
    amount: float
    category: str
    description: str
    is_income: bool
    date: str


class QuestionnaireModel(QuestionnaireBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class Answers(BaseModel):
    answers: list[str] | str


class QuestionnaireResult(BaseModel):
    graphs: list[str]
    score: float
    message: str
    badge_image: str
    parsed_answers: list[str] = Field(default_factory=list)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]
models.Base.metadata.create_all(bind=engine)


def _calc_result(high: float, low: float, factor: float) -> float:
    return (high - low) * factor + low


def _normalize_answers(raw_answers: list[str] | str) -> list[str]:
    if isinstance(raw_answers, str):
        try:
            parsed = json.loads(raw_answers)
        except json.JSONDecodeError:
            parsed = json.loads(raw_answers.replace("'", '"'))
    else:
        parsed = raw_answers

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail="Answers must be a list of strings.")

    normalized = [str(item).strip() for item in parsed if str(item).strip()]
    if len(normalized) != 5:
        raise HTTPException(
            status_code=400,
            detail="Exactly 5 questionnaire answers are required.",
        )

    return normalized


def _expand_answers(answers: list[str]) -> list[str]:
    try:
        transport_mode, transport_frequency = [
            value.strip() for value in answers[0].split(",", maxsplit=1)
        ]
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="The transportation answer must include the mode and a slider value.",
        ) from exc

    return [
        transport_mode,
        transport_frequency,
        answers[1],
        answers[2],
        answers[3],
        answers[4],
    ]


def _question_one(parts: list[str]) -> float:
    transport_mode = parts[0]
    frequency = float(parts[1])

    if transport_mode == "Combustion Engine Vehicle":
        return _calc_result(6.24, 1.56, frequency)
    if transport_mode == "Electric Powered Car":
        return _calc_result(0.054, 0.0135, frequency)
    if transport_mode == "Public Transport":
        return _calc_result(1.288, 0.307, frequency)
    if transport_mode == "Bicycle":
        return _calc_result(0.1553, 0.038325, frequency)
    raise HTTPException(status_code=400, detail=f"Unsupported transportation mode: {transport_mode}")


def _question_two(parts: list[str]) -> float:
    flights = parts[2]
    if flights == "4 or more":
        return 1.0

    flight_count = float(flights)
    score_map = {
        0.0: 0.0,
        1.0: 0.25,
        2.0: 0.5,
        3.0: 0.75,
    }
    return score_map.get(flight_count, 0.0)


def _question_three(parts: list[str]) -> float:
    compost = parts[3]
    if compost == "Yes":
        return 0.004106035
    if compost == "No":
        return 0.055822917
    raise HTTPException(status_code=400, detail=f"Unsupported compost answer: {compost}")


def _question_four(parts: list[str]) -> float:
    return _calc_result(0.904, 0.226, float(parts[4]))


def _question_five(parts: list[str]) -> float:
    diet = parts[5]
    if diet == "Vegan":
        return 1.5
    if diet == "Vegetarian":
        return 1.7
    if diet == "Other diet":
        return 2.9
    raise HTTPException(status_code=400, detail=f"Unsupported diet answer: {diet}")


def _draw_graph(mean: float, std_dev: float, result: float) -> str:
    x_values = np.linspace(mean - 4 * std_dev, mean + 4 * std_dev, 1000)
    y_values = stats.norm.pdf(x_values, mean, std_dev)
    percentile = stats.norm.cdf(result, mean, std_dev)

    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.plot(x_values, y_values, label="Population curve", color="#174f37", linewidth=2)
    axis.axvline(x=result, color="#d97706", linestyle="--", label=f"Your value: {result:.2f}")
    axis.fill_between(
        x_values,
        y_values,
        where=(x_values > result),
        color="#f59e0b",
        alpha=0.35,
    )
    axis.set_title(
        f"Percentile above your result: {(1 - percentile):.1%}",
        fontsize=12,
    )
    axis.set_xlabel("Value")
    axis.set_ylabel("Probability density")
    axis.legend(loc="upper left")
    axis.grid(alpha=0.2)

    file_name = f"plot_{uuid.uuid4()}.png"
    file_path = GRAPH_DIR / file_name
    figure.tight_layout()
    figure.savefig(file_path, dpi=150)
    plt.close(figure)
    return f"/static/graphs/{file_name}"


def _percentile_score(result: float, mean: float, std_dev: float) -> float:
    percentile = stats.norm.cdf(result, mean, std_dev)
    return 1 - percentile


def _final_score_message(score: float) -> tuple[str, str]:
    if 0 <= score <= 5:
        return (
            "You're an Eco-Beginner! Just stepping into the world of green heroics.",
            "0-5.png",
        )
    if score <= 15:
        return (
            "You're a Sprout Hero! Your eco-journey is budding and already moving in the right direction.",
            "5-15.png",
        )
    if score <= 30:
        return (
            "You're a Recycle Ranger! Your sustainable habits are gaining real momentum.",
            "15-30.png",
        )
    if score <= 45:
        return (
            "You're an Eco-Explorer! You are building a solid foundation for a greener routine.",
            "30-45.png",
        )
    if score <= 60:
        return (
            "You're a Nature Guardian! Your choices are making a visible positive impact.",
            "45-60.png",
        )
    if score <= 75:
        return (
            "You're an Eco-Knight! Your sustainability habits are strong and consistent.",
            "60-75.png",
        )
    if score <= 85:
        return (
            "You're a Green Sage! Nearly at the pinnacle of eco-wisdom.",
            "75-85.png",
        )
    if score <= 90:
        return (
            "You're an Earth Avenger! A few more upgrades and you're near eco-perfection.",
            "85-90.png",
        )
    if score <= 95:
        return (
            "You're an Eco-Sentinel! You're setting the standard for environmental stewardship.",
            "90-95.png",
        )
    return (
        "Congratulations, Eco-Champion! You're leading by example with outstanding sustainable habits.",
        "95-100.png",
    )


def _calculate_questionnaire_result(raw_answers: list[str] | str) -> QuestionnaireResult:
    answers = _normalize_answers(raw_answers)
    parts = _expand_answers(answers)

    transport_score = _question_one(parts)
    flight_score = _question_two(parts)
    compost_score = _question_three(parts)
    recycle_score = _question_four(parts)
    diet_score = _question_five(parts)

    percentile_components = [
        _percentile_score(transport_score, 2.686471807, 1.5),
        _percentile_score(flight_score, 0.5, 0.25),
        _percentile_score(compost_score, 0.059928952, 0.03),
        _percentile_score(recycle_score, 0.452, 0.05),
        _percentile_score(diet_score, 2.74, 0.2),
    ]

    weighted_score = (
        percentile_components[0] * 0.225
        + percentile_components[1] * 0.375
        + percentile_components[2] * 0.2
        + percentile_components[3] * 0.1
        + percentile_components[4] * 0.1
    )
    score_percent = round(weighted_score * 100, 1)
    message, badge_image = _final_score_message(score_percent)

    graphs = [
        _draw_graph(2.686471807, 1.5, transport_score),
        _draw_graph(0.5, 0.25, flight_score),
        _draw_graph(0.059928952, 0.03, compost_score),
        _draw_graph(0.452, 0.05, recycle_score),
        _draw_graph(2.74, 0.2, diet_score),
    ]

    return QuestionnaireResult(
        graphs=graphs,
        score=score_percent,
        message=message,
        badge_image=badge_image,
        parsed_answers=parts,
    )


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/questionnaire/", response_model=QuestionnaireModel)
async def create_questionnaire(questionnaire: QuestionnaireBase, db: db_dependency):
    db_questionnaire = models.Questionnaire(**questionnaire.model_dump())
    db.add(db_questionnaire)
    db.commit()
    db.refresh(db_questionnaire)
    return db_questionnaire


@app.get("/questionnaire/", response_model=list[QuestionnaireModel])
async def read_questionnaire(db: db_dependency, skip: int = 0, limit: int = 100):
    return db.query(models.Questionnaire).offset(skip).limit(limit).all()


@app.post("/submit_answers", response_model=QuestionnaireResult)
async def submit_answers(submission: Answers) -> QuestionnaireResult:
    return _calculate_questionnaire_result(submission.answers)


@app.post("/computer-use/sessions", response_model=ComputerUseSessionResponse)
def create_computer_use_session(
    request: ComputerUseStartRequest,
) -> ComputerUseSessionResponse:
    return computer_use_manager.create_session(request)


@app.get("/computer-use/sessions/{session_id}", response_model=ComputerUseSessionResponse)
def get_computer_use_session(session_id: str) -> ComputerUseSessionResponse:
    return computer_use_manager.get_session(session_id)


@app.post(
    "/computer-use/sessions/{session_id}/continue",
    response_model=ComputerUseSessionResponse,
)
def continue_computer_use_session(session_id: str) -> ComputerUseSessionResponse:
    return computer_use_manager.continue_session(session_id)


@app.post(
    "/computer-use/sessions/{session_id}/approval",
    response_model=ComputerUseSessionResponse,
)
def approve_computer_use_session(
    session_id: str,
    request: ComputerUseApprovalRequest,
) -> ComputerUseSessionResponse:
    return computer_use_manager.resolve_approval(session_id, request)
