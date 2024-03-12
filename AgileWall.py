import sys
import json
import logging
import Octopus
import Tesla
import argparse

VERSION = "0.1"

_LOGGER = logging.getLogger("AgileWall")

# TODO - Check times are converted correctly for PW API
# TODO - Details of the OAuth 2 SSO used by Tesla and the implications for the app

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

args = parser.parse_args()

TARIFF = args.tariff[0]
AREA_CODE = args.area[0]
TESLA_ID = args.tesla_id[0]
VERBOSE = args.verbose
LIST_ONLY = args.list_only
DAY_OFFSET = args.delta

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
Peak = agile.get_peak_slots(agile_time_slots)
SuperOffPeak = agile.get_super_off_peak_slots(agile_time_slots)
OffPeak = agile.get_off_peak_slots(agile_time_slots)
MidPeak = agile.get_mid_peak_slots(agile_time_slots)

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

tou_offpeak = agile.build_tou_periods(OffPeak)
rate_offpeak = agile.get_average_rate(OffPeak)
if VERBOSE:
    agile.print_tou("Off-Peak", rate_offpeak, tou_offpeak)

tou_midpeak = agile.build_tou_periods(MidPeak)
rate_midpeak = agile.get_average_rate(MidPeak)
if VERBOSE:
    agile.print_tou("Mid-Peak", rate_midpeak, tou_midpeak)

tou_peak = agile.build_tou_periods(Peak)
rate_peak = agile.get_average_rate(Peak)
if VERBOSE:
    agile.print_tou("Peak", rate_peak, tou_peak)

# Build the Rate Type / Energy Charges structure 
#    - this is stored in a separate structure from the ToU time slots
tou_rates = agile.build_tou_rates(rate_super, rate_offpeak, rate_midpeak, rate_peak)

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
pw_tariff["seasons"]["Summer"]["tou_periods"]["OFF_PEAK"] = tou_offpeak
pw_tariff["seasons"]["Summer"]["tou_periods"]["PARTIAL_PEAK"] = tou_midpeak
pw_tariff["seasons"]["Summer"]["tou_periods"]["ON_PEAK"] = tou_peak

if VERBOSE:
    print("ToU Periods (Updated)")
    print("=====================")
    print(json.dumps(pw_tariff["seasons"]["Summer"]["tou_periods"], indent=4))

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
