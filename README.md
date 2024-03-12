# AgileWall
## TL;DR
A simple python utility to fetch the daily Octopus Agile Import Tariff and load it into the Tesla Powerwall 2.

## Background
This is a long (and some might say rambling) background to development of this utility - mainly to serve as my own *aide-mémoire* for when I come back to this code, but also to explain how I arrived at certain design decisions.

One of the challenges with using a Tesla Powerwall with the Octopus Agile tariff is that there is no official support or integration between them. 
My initial approach was to set up a time based usage tariff in the Powerwall by using the 365 day average data available on the [Energy Stats UK site](https://energy-stats.uk/octopus-agile-northern-scotland/).

While this approach works adequately most of the time, as it allows the Powerwall to leverage the Tesla usage learning algorithm, and allows it to respond to solar forecasts by saving capacity in the battery to capture solar generation.

However, that approach doesn't respond well when the Agile tariff varies outsite the "average" pattern, so I started to investigate how I could use the Agile future rates to configure the battery to more accurately follow the real Agile variations, while still leveraging Powerwall intelligence.

The Powerwall "Utility Rate Plan" supports 4 different tariff types which can be used to label the time slots in the plan which drive the battery charge/discharge behaviour:
* **Super Off-Peak** - Charge the battery and consume from the grid
* **Off-Peak** - Ok to consume from the Grid
* **Mid-Peak** - Prefer not to consume from the grid and use battery
* **Peak** - Don't consume from the grid if possible, and use battery storage

So the first challenge is finding a programatic way to put the 48 time slots in the Agile Import Tariff into these 4 rate type buckets. The graph below shows how I have chosen to split up the rates, based on calculated thresholds which will vary as the spread of prices varies.

![Rate Thresholds Graph](images/Agile-Utility-Bands-Graph.png)

The Average unit price is the midpoint in the separation of the rates, with Peak, Mid-Peak above that price, and Off-Peak, Super Off-Peak below that price.

* **Mid-Peak** - Price is above Average, but below a price which is mid-way between average and max price; basically 50% of the spread between Average and Max rate price.
* **Peak** - Price is above the mid-way point between Average and Max rate price.
* **Off-Peak** - Price is below Average, but above a price which is mid-way between average and min price; basically 50% of the spread between Average and Min rate price.
* **Super Off-Peak** - Price is below the mid-way point between Average and Min rate price.

**Bucket Time-Slot Merging** - At this stage there are 48 timeslots which are "bucketed" into the relevant tariff types, but loading 48 separate slots into the Powerwall Utility Rate Plan would look a mess, so the next phase optimises each bucket by merging contiguous time-slots. This merge process also calculates the average rate for the new merged slot, as this needs to uploaded to the Powerwall along with the time of use schedule. The end result is a smalled set of time slots which need to be uploaded, and as a result the rate plan view in the Tesla app should clearer and less cluttered.

**Note:** This bucketing approach seems to work pretty well (or at least well enough), and testing it on historical Agile rate data it does returm sensible results. There may be a smarter way to calculate which rate time slot goes into which rate "bucket" but this approach is pretty much the limit of my mathematical and statistical knowledge... 😉 

## Design Considerations
1. **Grid Import Only** - At this stage I'm primarily concerned with self-consumption of solar and load shifting of consumption, so this utility doesn't deal with exporting power. That said, the approach would be the same for the export side, and the Powerwall API to update the export schedule is the same one used in this utility (Time of Use API).
2. **UTC & Local Time** - The Agile Tariff API returns time-slots in UTC, whereas the Tesla Powerwall API works from Local Time, using whatever Time Zone is set in the Powerwall.
3. **Agile Tariff Time Period** - The Octopus Agile Tariff runs from 11pm to 11pm the following day, so this needs to be taken into account when the schedule is uploaded to the Powerwall, as it expects the tariffs to run from midnight to midnight. As a result, the upload to the Powerwall needs to happen just before 11pm - that way the full 24hr look-ahead for the battery is correct.
4. **Tesla API** - Manipulating the Time of Use & Rate Plan information on the Powerwall cannot be done through the local Gateway API connection, as a result the remote Tesla API must be used. This brings with it the added complexity of dealing with Tesla's OAuth 2.0 Single Sign-On service.

## Possible Future Features
* **Tweak Rate Selection Thresholds** - Monitor the effectiveness of the current approach to bucketing the rates and see if additional parameters are needed to adjust the thresholds.
* **Home Assistant Integration** - Add the ability to launch / monitor this utility from Home Assistant
* **Node-Red Integration** - Run / monitor this script from Node-Red

## External Libraries & Dependencies
This utility uses the [TeslaPy](https://github.com/tdorssers/TeslaPy) Library to access the Powerwall API and to handle the OAuth 2 authentication used by the Tesla API.

As a result of the above dependency and some language features used in this utility it will only work with **Python 3.10 or later**.

## Running the app

### Tesla OAuth Single Sign-On (SSO)
The [TeslaPy](https://github.com/tdorssers/TeslaPy) Library implements the OAuth SSO needed by the Tesla API, this means that when you first run the application it will prompt you to log on to your Tesla account using a supplied URL, you will then need to copy the resulting sign-on URL back to the console window. so the program can complete the sign-on.

You only need to carry out this step once, as the SSO refresh token will then be stored in the same folder as the program, in a file named **cache.json**

**TODO** Add example of screen output

### Important - Scheduling this Program

Because of the fact that the Octopus Agile Tariffs run from 11pm to 11pm the following day it is important to schedule this program to run just before 11pm to ensure that the tariff data sent to the Powerwall is as accurate as possible. Running the program at any other time will result in today's time-slots being overwritten with tomorrow's tarrif data.

If you want to check the changes that will be made, you can run the program with the -L option and it will provide a verbose output of all the tariff data and proposed changes **without sending it to the Powerwall.**

**Note:** The program always attempts to download the next day's Agile tariff, so if the program is run before this data is available on the Octopus API, the program will display an error message and exit.

### Command Line Parameters:

    **-t** \<Agile Tariff Code\>
    **-a** \<DNO Area Code\>
    **-i** \<Tesla ID\>
    **-L** List only - List the config changes without sending to the Powerwall (Turns on Verbose Output)
    **-v** Verbose Console Output


You can find your DNO code here if you don't know it - [DNO Codes Explained](https://energy-stats.uk/dno-region-codes-explained/)

**Agile Tariff Code** - If you don't know yours, use the included AgileCodes.py to list all the publicly available tariffs and their associated codes.

**Needless to say, you need to make sure that the Tariff Code and DNO Code are correct for your location otherwise the Agile Tariff data will be wrong...**

**Note:** To see the changes in the Tesla app, you'll need to restart it, as the app appears to cache the Utility Rate Plan and doesn't refresh automatically when it is changed via the API 

### Exit Codes
The program will signal success/failure by returning one of the following exit codes:

* **0** - Program Executed Successfully, new tariffs were fetched and uploaded to the Powerwall
* **1** - List mode completed successfully
* **-1** - Incorrect version of Python (must be 3.10 or later)
* **-2** - Agile Tariffs not available (happens if you run the program before 4pm)
* **-3** - Failed callinging Tesla Powerwall API
* **-4** - P

## Screen Shots
When you have uploaded the Agile tariff data, you should see something like this on the Tesla iPhone app:
![Tesla App Screenshot](images/Tesla-App.png)
