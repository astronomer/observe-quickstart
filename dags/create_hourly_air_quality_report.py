"""DAG that creates an hourly air quality report containing the 
average PM2.5 and PM10 values for each hour of the last day."""

import logging
from datetime import datetime, timedelta

from airflow.decorators import dag, task
from airflow.models.dataset import Dataset
from airflow.models.param import Param


# get the airflow.task logger
t_log = logging.getLogger("airflow.task")


@dag(
    start_date=datetime(2025, 1, 1),
    schedule="0 * * * *",  # runs every hour
    max_active_runs=1,
    catchup=False,
    doc_md=__doc__,
    params={
        "delay_aq_fetch": Param(
            False,
            type="boolean",
            description="Whether to delay the API call to fetch the air quality data by 61 minutes",
        ),
    },
)
def create_aq_report():

    @task(inlets=[Dataset("aq_data")])
    def get_aq_data_last_day(**context):
        """
        Fetches the latest air quality data from the csv file.
        Returns:
            dict: The latest air quality data.
        """
        import os
        import csv
        import time
        from airflow.exceptions import AirflowSkipException

        delay_aq_fetch = context["params"]["delay_aq_fetch"]
        if delay_aq_fetch:
            time.sleep(60 * 61)

        # ts is the timestamp that marks the start of this DAG run's data interval
        # (when the previous DAG run happened),
        # the DAG runs once every hour, so we need to subtract another 23
        # to get the timstamp for 24 hours before the actual DAG run
        timestamp = context["ts"]
        cutoff_time = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z") - timedelta(
            hours=23
        )

        # skip if the file does not exist
        if os.path.isfile("include/aq_data.csv") is False:
            raise AirflowSkipException("No air quality data available")

        with open("include/aq_data.csv", "r") as file:
            reader = csv.DictReader(file)
            data = list(reader)

        # filter data for the last week
        last_day_aq_data = [
            row
            for row in data
            if datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%S%z") >= cutoff_time
        ]

        return last_day_aq_data

    @task
    def caluclate_avg_aq_per_hour(last_day_aq_data: dict, **context) -> dict:
        """
        Calculates the average air quality values per hour in the last day.
        """

        timestamp = context["ts"]
        current_hour = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S%z").hour
        last_24_hours = [(current_hour - i) % 24 for i in range(24)]

        avg_aq_per_hour = {}

        for hour in last_24_hours:
            data_for_hour = [
                row
                for row in last_day_aq_data
                if datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%S%z").hour
                == hour
            ]

            pm2_5_values = [float(row["pm2_5"]) for row in data_for_hour]
            pm10_values = [float(row["pm10"]) for row in data_for_hour]

            if len(pm2_5_values) != 0:
                avg_pm2_5 = sum(pm2_5_values) / len(pm2_5_values)
            else:
                avg_pm2_5 = "NO DATA"

            if len(pm10_values) != 0:
                avg_pm10 = sum(pm10_values) / len(pm10_values)
            else:
                avg_pm10 = "NO DATA"

            avg_aq_per_hour[str(hour)] = {
                "avg_pm2_5": avg_pm2_5,
                "avg_pm10": avg_pm10,
            }

        return avg_aq_per_hour

    @task(
        outlets=[Dataset("aq_report")],
    )
    def send_aq_report(avg_aq_per_hour: dict, **context):
        """
        Mocks sending the air quality report to the team.
        """
        day = context["ts"].split("T")[0]

        for entry in avg_aq_per_hour:
            t_log.info(
                f"Day {day} Hour {entry}: PM2.5: {avg_aq_per_hour[entry]['avg_pm2_5']}, PM10: {avg_aq_per_hour[entry]['avg_pm10']}"
            )

    _get_aq_data_last_week = get_aq_data_last_day()
    _caluclate_avg_aq_per_hour = caluclate_avg_aq_per_hour(_get_aq_data_last_week)
    send_aq_report(_caluclate_avg_aq_per_hour)


create_aq_report()
