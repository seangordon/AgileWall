import sys
import json
import logging
import Octopus
import Tesla
import argparse
import ChartGen

VERSION = "0.4"

_LOGGER = logging.getLogger("AgileWall")

if not sys.version_info >= (3, 11):
    print("This program uses features which require Python 3.11 or later.")
    exit(-1)


parser = argparse.ArgumentParser(description=f"Octopus Agile to Tesla Powerwall Integration v{VERSION}")
parser.add_argument("-t", "--tariff", nargs=1, dest="tariff", type=str, required=True,
                    help="Octopus Agile Tariff code, e.g. AGILE-23-12-06")
parser.add_argument("-a", "--area", nargs=1, dest="area", type=str, required=True,
                    help="DNO Area Code - see https://energy-stats.uk/dno-region-codes-explained/")
parser.add_argument("-i", "--tesla_id", nargs=1, dest="tesla_id", type=str, required=True,
                    help="Tesla logon ID - used to sign on to your Tesla account.")
parser.add_argument("-v", "--verbose", help="Verbose Output", action="store_true", default=False)
parser.add_argument("-L", "--list_only", help="List Changes, but don't send to Powerwall",
                    action="store_true", default=False)
parser.add_argument("-d", "--delta", default=0, dest="delta", type=int, 
                    help="Days into the past to fetch Agile Schedule - Does not update Powerwall (Useful for testing)")
parser.add_argument("-c", "--chart", help="Generate Chart Data", action="store_true", default=False)
parser.add_argument("-o", "--chart_path", default=".", dest="chart_path", type=str, 
                    help="Path to write the chart files to.")
parser.add_argument("-P", "--peak", help="Combine Mid-Peak & Peak Bands", action="store_true", default=False)

args = parser.parse_args()

TARIFF = args.tariff[0]
AREA_CODE = args.area[0]
TESLA_ID = args.tesla_id[0]
VERBOSE = args.verbose
LIST_ONLY = args.list_only
DAY_OFFSET = args.delta
CHART_GEN = args.chart
CHART_PATH = args.chart_path
PEAK_COMBINE = args.peak

if DAY_OFFSET != 0:  # Requesting past days Agile schedules means we must not update the Powerwall
    LIST_ONLY = True

if LIST_ONLY:       # Turn on verbose output if we are just listing the changes
    VERBOSE = True

_LOGGER.info(f"Tariff = {TARIFF}")
_LOGGER.info(f"DNO Area = {AREA_CODE}")
_LOGGER.info(f"Tesla ID = {TESLA_ID}")

# Create the Agile instance and pass in the Logger we are using
agile = Octopus.Agile(_LOGGER)

# Fetch tomorrow's Agile Tariff - This function also sets the various thresholds
# which are used to bucket the time slots later.
agile_time_slots = agile.get_agile_rates(TARIFF, AREA_CODE, 0-DAY_OFFSET)
if not agile_time_slots:
    print("No Agile Tariff found for today, please try again later.")
    exit(-2)

# Sort the time slots into one of the 4 Utility Plan codes
SuperOffPeak = agile.get_super_off_peak_slots(agile_time_slots)
OffPeak = agile.get_off_peak_slots(agile_time_slots)

# Are we combining the Mid-Peak & Peak Tariff Bands?
if PEAK_COMBINE:
    Peak = agile.get_combined_peak_slots(agile_time_slots)
    MidPeak = []
else:
    MidPeak = agile.get_mid_peak_slots(agile_time_slots)
    Peak = agile.get_peak_slots(agile_time_slots)

if VERBOSE:
    print()
    print(f"Time Slots: {len(agile_time_slots)}")
    print("==============")
    agile.print_rate_slots("Super Off-Peak", SuperOffPeak)
    agile.print_rate_slots("Off-Peak", OffPeak)
    agile.print_rate_slots("Mid-Peak", MidPeak)
    agile.print_rate_slots("Peak", Peak)

# Process each bucket and merge any adjacent time slots
SuperOffPeak = agile.merge_adjacent_slots(SuperOffPeak)
OffPeak = agile.merge_adjacent_slots(OffPeak)
MidPeak = agile.merge_adjacent_slots(MidPeak)
Peak = agile.merge_adjacent_slots(Peak)

if VERBOSE:
    slot_count = len(SuperOffPeak)+len(OffPeak)+len(MidPeak)+len(Peak)
    print()
    print(f"Merged Slots: {slot_count}")
    print("================")
    agile.print_rate_slots("Super Off-Peak", SuperOffPeak)
    agile.print_rate_slots("Off-Peak", OffPeak)
    agile.print_rate_slots("Mid-Peak", MidPeak)
    agile.print_rate_slots("Peak", Peak)

# Build the Tesla Time of Use data and calculate the average rate for each rate type
tou_super = agile.build_tou_periods(SuperOffPeak)
rate_super = agile.get_average_rate(SuperOffPeak)
if VERBOSE:
    agile.print_tou("Super Off-Peak", rate_super, tou_super)

tou_off_peak = agile.build_tou_periods(OffPeak)
rate_off_peak = agile.get_average_rate(OffPeak)
if VERBOSE:
    agile.print_tou("Off-Peak", rate_off_peak, tou_off_peak)

tou_mid_peak = agile.build_tou_periods(MidPeak)
tou_peak = agile.build_tou_periods(Peak)

if PEAK_COMBINE:
    rate_mid_peak = round(agile.MAX, 3)
    rate_peak = round(agile.MAX, 3)
else:
    rate_mid_peak = agile.get_average_rate(MidPeak)
    rate_peak = agile.get_average_rate(Peak)

if VERBOSE:
    agile.print_tou("Mid-Peak", rate_mid_peak, tou_mid_peak)
    agile.print_tou("Peak", rate_peak, tou_peak)

# Build the Rate Type / Energy Charges structure 
#    - this is stored in a separate structure from the ToU time slots
tou_rates = agile.build_tou_rates(rate_super, rate_off_peak, rate_mid_peak, rate_peak)

# Fetch the current Powerwall Battery Tariff data from Tesla
# The Update API takes the entire tariff configuration structure as input, so fetch
# all the current config, and update only the sections we care about - all other
# config options in this structure are unchanged
powerwall = Tesla.Powerwall(TESLA_ID)
pw_tariff = powerwall.get_tariff()

if VERBOSE:
    print("Energy Charges")
    print("==============")
    print(json.dumps(pw_tariff["energy_charges"]["Summer"], indent=4))

    print("New ToU Rates")
    print("=============")
    print(json.dumps(tou_rates, indent=4))

# Update PW Energy Charges Data section
pw_tariff["energy_charges"]["Summer"] = tou_rates

if VERBOSE:
    print("Energy Charges (Updated)")
    print("========================")
    print(json.dumps(pw_tariff["energy_charges"]["Summer"], indent=4))

    print("ToU Periods")
    print("===========")
    print(json.dumps(pw_tariff["seasons"]["Summer"]["tou_periods"], indent=4))

# Update ToU Slots in the Battery Tariff data
pw_tariff["seasons"]["Summer"]["tou_periods"]["SUPER_OFF_PEAK"] = tou_super
pw_tariff["seasons"]["Summer"]["tou_periods"]["OFF_PEAK"] = tou_off_peak
pw_tariff["seasons"]["Summer"]["tou_periods"]["PARTIAL_PEAK"] = tou_mid_peak
pw_tariff["seasons"]["Summer"]["tou_periods"]["ON_PEAK"] = tou_peak

if VERBOSE:
    print("ToU Periods (Updated)")
    print("=====================")
    print(json.dumps(pw_tariff["seasons"]["Summer"]["tou_periods"], indent=4))

if CHART_GEN:
    if not ChartGen.export_agile_data(agile_time_slots, CHART_PATH):
        print("Error writing chart time slot data.")
        exit(-4)

    if not ChartGen.export_agile_rates(agile.MIN, agile.MAX, agile.LIMIT_SUPER_OFF_PEAK, agile.LIMIT_OFF_PEAK,
                                       agile.LIMIT_MID_PEAK, PEAK_COMBINE, CHART_PATH):
        print("Error writing chart pw rate data.")
        exit(-4)

# Don't send the changes to the Powerwall if we are just listing the changes
if LIST_ONLY:
    print("List Mode Complete - No Updates Applied.")
    exit(1)

# Send the changes to the Powerwall API
res = powerwall.set_tariff(pw_tariff)
if not res == "Updated":
    _LOGGER.error("Failed to update Powerwall Battery Tariff data.")
    exit(-3)

print("Tesla Powerwall Battery Tariff data successfully updated.")
exit(0)
