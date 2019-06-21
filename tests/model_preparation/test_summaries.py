import json
import os
import random

from tempfile import TemporaryDirectory
from unittest import TestCase

import pandas as pd

from hypothesis import (
    given,
    HealthCheck,
    settings,
)
from hypothesis.strategies import (
    just,
    integers,
)

from oasislmf.manager import OasisManager as om
from oasislmf.model_preparation.summaries import write_exposure_summary
from oasislmf.model_preparation.gul_inputs import get_gul_input_items
from oasislmf.utils.coverages import SUPPORTED_COVERAGE_TYPES
from oasislmf.utils.peril import PERILS
from oasislmf.utils.profiles import get_oed_hierarchy
from oasislmf.utils.status import OASIS_KEYS_STATUS

from tests.data import (
    keys,
    source_exposure,
    write_source_files,
    write_keys_files,
)

PERIL_LS = [
    'extra tropical cyclone',
    'earthquake',
    'flash flood'
]
COVERAGE_TYPE_IDS = [v['id'] for k, v in SUPPORTED_COVERAGE_TYPES.items()]
MAX_NLOCATIONS = 6
MAX_NKEYS = len(PERIL_LS) * len(COVERAGE_TYPE_IDS) * MAX_NLOCATIONS


class TestSummaries(TestCase):

    @settings(deadline=None, suppress_health_check=[HealthCheck.too_slow])
    @given(
        exposure=source_exposure(
            from_account_ids=just('1'),
            from_portfolio_ids=just('1'),
            from_location_perils=just('WTC;WEC;BFR;OO1'),
            from_location_perils_covered=just('WTC;WEC;BFR;OO1'),
            from_country_codes=just('US'),
            from_area_codes=just('CA'),
            from_building_tivs=integers(1000, 1000000),
            from_building_deductibles=just(0),
            from_building_min_deductibles=just(0),
            from_building_max_deductibles=just(0),
            from_building_limits=just(0),
            from_other_tivs=integers(100, 100000),
            from_other_deductibles=just(0),
            from_other_min_deductibles=just(0),
            from_other_max_deductibles=just(0),
            from_other_limits=just(0),
            from_contents_tivs=integers(50, 50000),
            from_contents_deductibles=just(0),
            from_contents_min_deductibles=just(0),
            from_contents_max_deductibles=just(0),
            from_contents_limits=just(0),
            from_bi_tivs=integers(20, 20000),
            from_bi_deductibles=just(0),
            from_bi_min_deductibles=just(0),
            from_bi_max_deductibles=just(0),
            from_bi_limits=just(0),
            from_sitepd_deductibles=just(0),
            from_sitepd_min_deductibles=just(0),
            from_sitepd_max_deductibles=just(0),
            from_sitepd_limits=just(0),
            from_siteall_deductibles=just(0),
            from_siteall_min_deductibles=just(0),
            from_siteall_max_deductibles=just(0),
            from_siteall_limits=just(0),
            size=MAX_NLOCATIONS
        ),
        keys=keys(
            from_statuses=just(OASIS_KEYS_STATUS['success']['id']),
            size=MAX_NKEYS
        )
    )
    def test_write_exposure_summary(self, exposure, keys):
        """
        Test write_exposure_summary method. Create keys and keys errors files
        with random perils and coverage types. At least one key given success
        status. Remaining keys given either fail or nomatch statuses.

        Arithmentic within output file tested.
        """

        # Use current system time to set random seed
        random.seed(None)

        # Create keys and keys errors files with random perils and coverage
        # types. At least one key given success status.
        model_perils = random.sample(
            PERIL_LS,
            random.randint(1, len(PERIL_LS))
        )
        model_peril_ids = [PERILS[peril]['id'] for peril in model_perils]
        model_coverage_types = random.sample(
            COVERAGE_TYPE_IDS,
            random.randint(1, len(COVERAGE_TYPE_IDS))
        )
        success_nlocations = random.randint(1, MAX_NLOCATIONS)
        # Remaining keys given either fail or nomatch statuses
        if success_nlocations != MAX_NLOCATIONS:
            fail_nlocations = random.randint(0, MAX_NLOCATIONS - success_nlocations)
            MAX_NLOCATIONS - success_nlocations - fail_nlocations
        else:
            fail_nlocations = 0

        keys_per_loc = len(model_peril_ids) * len(model_coverage_types)
        successes = keys[:success_nlocations * keys_per_loc]
        nonsuccesses = keys[success_nlocations * keys_per_loc:MAX_NLOCATIONS * keys_per_loc]
        for row, key in enumerate(successes):
            key['locnumber'] = row // keys_per_loc + 1
            key['peril_id'] = model_peril_ids[(row // len(model_coverage_types)) % len(model_peril_ids)]
            key['coverage_type'] = model_coverage_types[row % len(model_coverage_types)]
        if len(nonsuccesses) != 0:
            for row, key in enumerate(nonsuccesses):
                key['locnumber'] = row // keys_per_loc + 1 + success_nlocations
                key['peril_id'] = model_peril_ids[(row // len(model_coverage_types)) % len(model_peril_ids)]
                key['coverage_type'] = model_coverage_types[row % len(model_coverage_types)]
                if key['locnumber'] <= (success_nlocations + fail_nlocations):
                    key['status'] = OASIS_KEYS_STATUS['fail']['id']
                else:
                    key['status'] = OASIS_KEYS_STATUS['nomatch']['id']
        else:   # If all keys have success status
            nonsuccesses = [{}]

        with TemporaryDirectory() as d:

            # Prepare arguments for write_exposure_summary
            target_dir = os.path.join(d, 'inputs')
            os.mkdir(target_dir)

            keys_fp = os.path.join(d, 'keys.csv')
            keys_errors_fp = os.path.join(d, 'keys_errors.csv')
            write_keys_files(
                keys=successes,
                keys_file_path=keys_fp,
                keys_errors=nonsuccesses,
                keys_errors_file_path=keys_errors_fp
            )

            # If keys errors file empty then drop empty rows and preserve
            # headings
            if not any(nonsuccesses):
                nonsuccesses_df = pd.read_csv(keys_errors_fp)
                nonsuccesses_df.drop([0], axis=0).to_csv(
                    keys_errors_fp,
                    index=False,
                    encoding='utf-8'
                )

            exposure_fp = os.path.join(d, 'exposure.csv')
            write_source_files(exposure=exposure, exposure_fp=exposure_fp)

            self.manager = om()
            exposure_profile = self.manager.exposure_profile

            gul_inputs_df, exposure_df = get_gul_input_items(
                exposure_fp, keys_fp, exposure_profile
            )

            oed_hierarchy = get_oed_hierarchy(exposure_profile=exposure_profile)

            # Execute method
            write_exposure_summary(
                target_dir,
                gul_inputs_df,
                exposure_df,
                exposure_fp,
                keys_errors_fp,
                exposure_profile,
                oed_hierarchy
            )

            # Get output file for testing
            output_filename = target_dir + "/exposure_summary_report.json"
            with open(output_filename) as f:
                data = json.load(f)

            # Test integrity of output file
            # Loop over all modelled perils
            for peril in model_perils:
                # Test modelled peril is in output file
                self.assertIn(peril, data.keys())

                tiv_per_peril = 0
                tiv_per_coverage = {}
                total_nlocations = 0

                # Loop over all keys statuses
                for status in OASIS_KEYS_STATUS.values():
                    status_id = status['id']
                    tiv_per_status = 0

                    # Loop over all supported coverage types
                    for coverage_type in SUPPORTED_COVERAGE_TYPES.keys():
                        coverage_tiv = data[peril][status_id]['tiv_by_coverage'][coverage_type]
                        tiv_per_status += coverage_tiv
                        if coverage_type in tiv_per_coverage.keys():
                            tiv_per_coverage[coverage_type] += coverage_tiv
                        else:
                            tiv_per_coverage[coverage_type] = coverage_tiv

                    # Test sum of TIV by coverage per status
                    self.assertEqual(
                        tiv_per_status,
                        data[peril][status_id]['tiv']
                    )

                    tiv_per_peril += tiv_per_status
                    total_nlocations += data[peril][status_id]['number_of_locations']

                # Test sum of TIV by status per peril
                self.assertEqual(tiv_per_peril, data[peril]['all']['tiv'])

                # Loop over all supported coverage types
                for coverage_type in SUPPORTED_COVERAGE_TYPES.keys():

                    # Test sum of TIV by coverage and status per peril
                    self.assertEqual(
                        tiv_per_coverage[coverage_type],
                        data[peril]['all']['tiv_by_coverage'][coverage_type]
                    )

                # Test sum of number of locations per status
                self.assertEqual(
                    total_nlocations,
                    data[peril]['all']['number_of_locations']
                )