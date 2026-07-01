from hidden_jobs_worker.adapters.ashby import AshbyAdapter
from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.adapters.comeet import ComeetAdapter
from hidden_jobs_worker.adapters.greenhouse import GreenhouseAdapter
from hidden_jobs_worker.adapters.lever import LeverAdapter
from hidden_jobs_worker.adapters.personio import PersonioAdapter
from hidden_jobs_worker.adapters.recruitee import RecruiteeAdapter
from hidden_jobs_worker.adapters.smartrecruiters import SmartRecruitersAdapter
from hidden_jobs_worker.adapters.teamtailor import TeamtailorAdapter
from hidden_jobs_worker.adapters.workable import WorkableAdapter
from hidden_jobs_worker.models import AtsType, CareerBoard


class AtsAdapterManager:
    def __init__(self, adapters: list[AtsAdapter] | None = None) -> None:
        configured_adapters = adapters or [
            GreenhouseAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            WorkableAdapter(),
            SmartRecruitersAdapter(),
            TeamtailorAdapter(),
            RecruiteeAdapter(),
            ComeetAdapter(),
            PersonioAdapter(),
        ]
        self._adapters = {adapter.ats_type: adapter for adapter in configured_adapters}

    def get_adapter(self, career_board: CareerBoard) -> AtsAdapter | None:
        return self._adapters.get(career_board.ats_type)

    def supports(self, ats_type: AtsType) -> bool:
        return ats_type in self._adapters
