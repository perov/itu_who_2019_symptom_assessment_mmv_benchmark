# This is a component of the MMVB for the "Symptom assessment" sub-group
# (of the the International Telecommunication Union focus group
# "Artificial Intelligence for Health".
# For copyright and licence, see the parent directory.

import glob
import hashlib
import json
import os
import time

import requests

from evaluator.benchmark.manager import BenchmarkManager
from evaluator.benchmark.exceptions import SetupError
from evaluator.benchmark.utils import create_dirs
from evaluator.benchmark.definitions import ManagerStatuses

SERVER_HOST_FOR_CASE_GENERATION = "http://0.0.0.0:5001"

TIMEOUT = 0.5  # in seconds

FILE_DIR = os.path.dirname((os.path.abspath(__file__)))

AI_LOCATION_ALPHA = "http://127.0.0.1:5002/toy-ai/v1/solve-case"

AI_TYPES_TO_LOCATIONS = {
    "toy_ai_random_uniform": AI_LOCATION_ALPHA,
    "toy_ai_random_probability_weighted": AI_LOCATION_ALPHA,
    "toy_ai_deterministic_most_likely_conditions": AI_LOCATION_ALPHA,
    "toy_ai_deterministic_by_symptom_intersection": AI_LOCATION_ALPHA,
    "toy_ai_faulty_random_uniform": AI_LOCATION_ALPHA
}

# TODO: make this configurable each ai can implement and have its own root url
# TODO: as well as its own health check and solve case endpoints
AI_TYPES_ENDPOINTS = {
    'toy_ai_random_uniform': {
        'root': 'http://127.0.0.1:5002/toy-ai/v1/',
        'health_check': 'health-check',
        'solve_case': 'solve-case',
    },
    'toy_ai_random_probability_weighted': {
        'root': 'http://127.0.0.1:5002/toy-ai/v1/',
        'health_check': 'health-check',
        'solve_case': 'solve-case',
    },
    'toy_ai_deterministic_most_likely_conditions': {
        'root': 'http://127.0.0.1:5002/toy-ai/v1/',
        'health_check': 'health-check',
        'solve_case': 'solve-case',
    },
    'toy_ai_deterministic_by_symptom_intersection': {
        'root': 'http://127.0.0.1:5002/toy-ai/v1/',
        'health_check': 'health-check',
        'solve_case': 'solve-case',
    },
    'toy_ai_faulty_random_uniform': {
        'root': 'http://127.0.0.1:5002/toy-ai/v1/',
        'health_check': 'health-check',
        'solve_case': 'solve-case',
    }
}

BENCHMARK_MANAGER = BenchmarkManager()


def get_unique_id():
    return str(time.time()).replace(".", "_")


def parse_validate_caseSetId(caseSetId):
    case_set_id = str(caseSetId)
    for char in case_set_id:
        assert char in [str(x) for x in range(10)] or char == "_"
    return case_set_id


def md5(value):
    return hashlib.md5(value.encode()).hexdigest()


def generate_case_set(request):
    num_cases = int(request["numCases"])
    # TODO: Gracefully fail for >1000 cases
    assert num_cases > 0 and num_cases <= 1000

    cases = []

    for case_id in range(num_cases):
        request = requests.get(
            SERVER_HOST_FOR_CASE_GENERATION + "/case-generator/v1/generate-case"
        )
        assert request.status_code == 200
        cases.append(request.json())

    case_set_id = get_unique_id()
    path = os.path.join(FILE_DIR, "data", case_set_id)

    create_dirs(path)

    json.dump(cases, open(os.path.join(path, "cases.json"), "w"), indent=2)

    return {"case_set_id": case_set_id}


def list_case_sets():
    path = os.path.join(FILE_DIR, "data/")

    return {
        "existing_case_sets": [
            element.replace(path, "") for element in glob.glob(path + "*")
        ]
    }


def extract_case_set(caseSetId):
    case_set_id = parse_validate_caseSetId(caseSetId)

    return {
        "cases": json.load(
            open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json"))
        )
    }


def list_all_ai_implementations():
    return {
        "ai_implementations": [
            {"name": ai_implementation_name}
            for ai_implementation_name in AI_TYPES_TO_LOCATIONS.keys()
        ]
    }


def run_case_set_against_ais(request):
    """Runs a given case set against a given set of AIs"""

    if BENCHMARK_MANAGER.state == ManagerStatuses.IDLE:
        case_set_id = parse_validate_caseSetId(request["caseSetId"])
        ai_implementations = request["aiImplementations"]
        results = []

        for ai in ai_implementations:
            assert ai in AI_TYPES_ENDPOINTS, f'AI {ai} not recognised/configured'

        unique_id = get_unique_id()
        benchmarked_ais = {
            ai: AI_TYPES_ENDPOINTS[ai]
            for ai in ai_implementations
        }

        cases = json.load(
            open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json"))
        )

        try:
            BENCHMARK_MANAGER.setup(unique_id, case_set_id, cases, benchmarked_ais)
        except SetupError:
            unique_id = BENCHMARK_MANAGER.benchmark_id
            # at this point we might also like to take the case set being run and
            # load it into the UI proper container
            return {'run_id': unique_id, 'status': int(ManagerStatuses.RUNNING)}
        else:
            output = BENCHMARK_MANAGER.run_benchmark()
            results = output['results']
            json.dump(
                results,
                open(os.path.join(FILE_DIR, "data", case_set_id, "results.json"), "w"),
                indent=2)

        results_by_ai = {}
        if results:
            for _, ais_results in results.items():
                for ai_name, ai_result in ais_results.items():
                    results_by_ai.setdefault(ai_name, []).append(ai_result['result'])

        return {
            'run_id': unique_id,
            'case_set_id': case_set_id,
            'case_set': cases,
            'status': int(ManagerStatuses.IDLE),
            'results_by_ai': results_by_ai
            }
    else:
        return {
            'run_id': BENCHMARK_MANAGER.benchmark_id,
            'case_set_id': BENCHMARK_MANAGER.case_set_id,
            'case_set': {'cases': BENCHMARK_MANAGER.case_set},
            'status': int(ManagerStatuses.RUNNING),
            'results_by_ai': {}
            }


def run_case_set_against_ai(request):
    case_set_id = parse_validate_caseSetId(request["caseSetId"])
    ai_implementation = request["aiImplementation"]
    run_name = request["runName"]

    assert ai_implementation in AI_TYPES_TO_LOCATIONS
    ai_location_path = AI_TYPES_TO_LOCATIONS[ai_implementation]

    run_hash = get_unique_id()

    path = os.path.join(FILE_DIR, "data", case_set_id, run_hash)

    cases = json.load(open(os.path.join(FILE_DIR, "data", case_set_id, "cases.json")))

    results = []

    for case in cases:
        try:
            request = requests.post(
                ai_location_path,
                json={
                    "aiImplementation": ai_implementation,
                    "caseData": case["caseData"],
                },
                timeout=TIMEOUT,
            )

            assert request.status_code == 200
            response = request.json()
        except AssertionError:
            response = None

        results.append(response)

    create_dirs(path)

    json.dump(
        {
            "ai_location_path": ai_location_path,
            "ai_implementation": ai_implementation,
            "run_name": run_name,
        },
        open(os.path.join(path, "meta.json"), "w"),
        indent=2,
    )

    json.dump(results, open(os.path.join(path, "results.json"), "w"), indent=2)

    return {"runId": run_hash, "results": results}


def report_update():
    manager = BENCHMARK_MANAGER
    report = manager.db_client.select_manager_report(
        benchmark_id=manager.benchmark_id, prefetch=True)

    collected_reports = {}
    for ai_report in report.ai_reports:
        collected_reports.setdefault(ai_report.ai_name, []).append(
            {
                'case_status': ai_report.case_status,
                'healthcheck_status': ai_report.healthcheck_status,
                'health_checks': ai_report.health_checks,
                'errors': ai_report.errors,
                'timeouts': ai_report.hard_timeouts
            }
        )

    results_file_path = os.path.join(
        FILE_DIR, "data", manager.case_set_id, "results.json")

    if manager.state == ManagerStatuses.IDLE and os.path.isfile(results_file_path):
        results = json.load(open(
            os.path.join(FILE_DIR, "data", manager.case_set_id, "results.json"), "r")
        )
        results_by_ai = {}
        if results:
            for _, ais_results in results.items():
                for ai_name, ai_result in ais_results.items():
                    results_by_ai.setdefault(ai_name, []).append(ai_result['result'])
    else:
        results_by_ai = {}

    return {
        'run_id': manager.benchmark_id,
        'case_set_id': manager.case_set_id,
        'total_cases': report.total_cases,
        'current_case_index': report.current_case_index,
        'current_case_id': report.current_case_id,
        'ai_reports': collected_reports,
        'results_by_ai': results_by_ai,
        'logs': manager.accumulated_logs
    }


def benchmark_status():
    return {'status': bool(int(BENCHMARK_MANAGER.state))}
