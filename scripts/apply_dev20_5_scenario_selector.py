#!/usr/bin/env python3
from pathlib import Path

R=Path(__file__).resolve().parents[1]
p=R/'apps/mobile/App.tsx'
s=p.read_text(encoding='utf-8')
const="""const VALIDATION_SCENARIOS = [
  'SMOKE_CAL_EMPTY', 'HUMAN_MOVING',
  'EMPTY_CAL', 'EMPTY_TEST', 'HUMAN_STATIONARY_CENTER',
  'HUMAN_NEAR_LENOVO', 'HUMAN_NEAR_PIXEL10', 'HUMAN_NEAR_PIXEL7',
  'HUMAN_OUTSIDE', 'NON_HUMAN_MOTION',
] as const;

"""
if 'const VALIDATION_SCENARIOS' not in s:
    anchor='export default function App() {'
    if anchor not in s: raise SystemExit('App component anchor missing')
    s=s.replace(anchor,const+anchor,1)
s=s.replace("const [validationScenario, setValidationScenario] = useState<'SMOKE_CAL_EMPTY'|'HUMAN_MOVING'|'UNSPECIFIED'>('UNSPECIFIED');","const [validationScenario, setValidationScenario] = useState<string>('UNSPECIFIED');",1)
old="""          <View style={s.card}><Text style={s.h2}>Scenario</Text><Text style={s.text}>{validationScenario}</Text>
            <View style={s.statusRow}><Pressable onPress={() => setValidationScenario('SMOKE_CAL_EMPTY')}><Text style={s.link}>EMPTY</Text></Pressable>
            <Pressable onPress={() => setValidationScenario('HUMAN_MOVING')}><Text style={s.link}>HUMAN MOVING</Text></Pressable></View></View>
"""
new="""          <View style={s.card}><Text style={s.h2}>Scenario</Text><Text style={s.text}>{validationScenario}</Text>
            <Pressable onPress={() => { const i = VALIDATION_SCENARIOS.indexOf(validationScenario as any); setValidationScenario(VALIDATION_SCENARIOS[(i + 1) % VALIDATION_SCENARIOS.length]); }}><Text style={s.link}>NEXT SCENARIO</Text></Pressable></View>
"""
if old in s:s=s.replace(old,new,1)
elif 'NEXT SCENARIO' not in s:raise SystemExit('scenario UI anchor missing')
p.write_text(s,encoding='utf-8')

d=R/'docs/TESTING_DEV20_5.md'
t=d.read_text(encoding='utf-8')
t=t.replace('4. Selecciona **EMPTY**. Ejecuta 60–90 s sin persona ni mover nodos; exporta 1 JSON/dispositivo.','4. En **Scenario**, pulsa **NEXT SCENARIO** hasta `SMOKE_CAL_EMPTY`. Ejecuta 60–90 s sin persona ni mover nodos; exporta 1 JSON/dispositivo.')
t=t.replace('5. Sin recalibrar ni mover nodos selecciona **HUMAN MOVING**. Ejecuta 60–90 s con una persona moviéndose dentro del triángulo; exporta 1 JSON/dispositivo.','5. Sin recalibrar ni mover nodos, pulsa **NEXT SCENARIO** hasta `HUMAN_MOVING`. Ejecuta 60–90 s con una persona moviéndose dentro del triángulo; exporta 1 JSON/dispositivo.')
t=t.replace('Congela commit/APK/detector/schema/parámetros. Dos días independientes × 9 escenarios × 3 dispositivos = 54 JSON frescos, >=330 s por escenario:','Congela commit/APK/detector/schema/parámetros. Dos días independientes × 9 escenarios × 3 dispositivos = 54 JSON frescos, >=330 s por escenario. Antes de cada corrida usa **NEXT SCENARIO** hasta que el nombre exacto del escenario quede visible:')
d.write_text(t,encoding='utf-8')
print('dev20.5 scenario selector applied')
