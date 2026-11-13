# Irrigation policy — bed 3

## Thresholds

| Soil moisture | Action |
|---|---|
| Above 50 per cent | Suspend irrigation. Running the system here risks waterlogging and root rot. |
| 30 to 50 per cent | Normal range. Run the standard schedule. |
| 20 to 30 per cent | Dry. Increase to twice daily if air temperature exceeds 30 degrees. |
| Below 20 per cent | Deficit. Run a manual cycle the same day and investigate the cause. |
| Below 12 per cent | Critical. Treat as a fault, not a weather event. Inspect filter, emitters and controller schedule before adding water. |

## Why the critical threshold is a fault, not a dry spell

Evapotranspiration alone will not take a correctly irrigated bed below about 18 per cent in this climate. A reading under 12 per cent means water is not reaching the roots, and adding more water through a blocked line achieves nothing. The September 2026 decline to 11 per cent was a controller schedule that had silently reverted after a firmware update, and three days were lost to the assumption that it was simply hot.

## Standard schedule

Once daily at 06:00 for 12 minutes. Morning irrigation is preferred: evening watering leaves foliage wet overnight and encourages fungal disease, and midday watering loses a substantial fraction to evaporation before it reaches the root zone.

## Hot-weather schedule

When air temperature exceeds 30 degrees on two consecutive days, move to twice daily at 06:00 and 18:00, 10 minutes each. Do not simply lengthen the morning cycle; beyond about 15 minutes the bed cannot absorb water as fast as it is delivered and the excess runs off.

Return to the standard schedule once temperature has been below 30 degrees for two consecutive days.

## After rainfall

Suspend irrigation while soil moisture remains above 50 per cent. Resume at the standard schedule when it falls back into the normal range. Do not resume on a fixed number of days after rain — resume on the reading.

## Alerting

Three conditions should raise an alert:

1. Soil moisture below 20 per cent at any reading.
2. A decline with no sawtooth for more than three consecutive days, which indicates irrigation is not reaching the bed even though moisture is still within range.
3. Any reading above 95 per cent, which usually means water has entered the probe cable rather than that the bed is flooded.

Condition 2 is the one most often missing from a monitoring setup, and it is the one that would have caught the September filter blockage on the third day rather than the ninth.
