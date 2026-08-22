#!/usr/bin/env python3
import json, pathlib, sys
ROOT=pathlib.Path(__file__).resolve().parents[2]

src=(ROOT/'apps/mobile/modules/body-finder-native/android/src/main/java/com/trochez/bodyfindernative/BodyFinderNativeModule.kt').read_text()
assert 'MAX_COMPLETED_VALIDATION_RUNS = 5' in src
assert 'completedRuns.addLast' in src and 'completedRuns.removeFirst' in src
assert 'snapshot_schema_version", 2' in src
assert 'selectedCompletedRunId' in src
assert 'validationTruthJson' in src
schema=json.load(open(ROOT/'protocol/schemas/validation-run-snapshot-v2.json'))
assert schema['properties']['snapshot_schema_version']['const']==2
fixture=json.load(open(ROOT/'validation/fixtures/dev11/new-run-preserves-previous-completed.json'))
assert fixture['completed'][0]['run_id']=='run-long' and fixture['completed'][1]['run_id']=='run-short'
print('PASS validation snapshot v2 contract')
