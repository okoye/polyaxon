# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function

import json
import uuid

from django.conf import settings

from polyaxon_schemas.utils import TaskType
from rest_framework import fields

from api.utils import config
from experiments.serializers import ExperimentJobSerializer

from spawner import K8SSpawner
from experiments.models import ExperimentJob
from spawner.utils.constants import ExperimentLifeCycle


def start_experiment(experiment):
    # Update experiment status to show that its started
    experiment.set_status(ExperimentLifeCycle.SCHEDULED)

    project = experiment.project
    group = experiment.experiment_group

    # Use spawner to start the experiment
    spawner = K8SSpawner(project_name=project.unique_name,
                         experiment_name=experiment.unique_name,
                         experiment_group_name=group.unique_name if group else None,
                         project_uuid=project.uuid.hex,
                         experiment_group_uuid=group.uuid.hex if group else None,
                         experiment_uuid=experiment.uuid.hex,
                         spec_config=experiment.config,
                         k8s_config=settings.K8S_CONFIG,
                         namespace=settings.K8S_NAMESPACE,
                         in_cluster=True,
                         use_sidecar=True,
                         sidecar_config=config.get_requested_params(to_str=True))
    resp = spawner.start_experiment()

    # Get the number of jobs this experiment started
    master = resp[TaskType.MASTER]
    job_uuid = master['pod']['metadata']['labels']['job_uuid']
    job_uuid = uuid.UUID(job_uuid)

    def get_definition(definition):
        serializer = ExperimentJobSerializer(data={
            'definition': json.dumps(definition, default=fields.DateTimeField().to_representation)
        })
        serializer.is_valid()
        return json.loads(serializer.validated_data['definition'])

    ExperimentJob.objects.create(uuid=job_uuid,
                                 experiment=experiment,
                                 definition=get_definition(master))
    for worker in resp[TaskType.WORKER]:
        job_uuid = worker['pod']['metadata']['labels']['job_uuid']
        job_uuid = uuid.UUID(job_uuid)
        ExperimentJob.objects.create(uuid=job_uuid,
                                     experiment=experiment,
                                     definition=get_definition(worker))
    for ps in resp[TaskType.PS]:
        job_uuid = ps['pod']['metadata']['labels']['job_uuid']
        job_uuid = uuid.UUID(job_uuid)
        ExperimentJob.objects.create(uuid=job_uuid,
                                     experiment=experiment,
                                     definition=get_definition(ps))


def stop_experiment(experiment, update_status=False):
    project = experiment.project
    group = experiment.experiment_group
    spawner = K8SSpawner(project_name=project.unique_name,
                         experiment_name=experiment.unique_name,
                         experiment_group_name=group.unique_name if group else None,
                         project_uuid=project.uuid.hex,
                         experiment_group_uuid=group.uuid.hex if group else None,
                         experiment_uuid=experiment.uuid.hex,
                         spec_config=experiment.config,
                         k8s_config=settings.K8S_CONFIG,
                         namespace=settings.K8S_NAMESPACE,
                         in_cluster=True,
                         use_sidecar=True,
                         sidecar_config=config.get_requested_params(to_str=True))
    spawner.stop_experiment()
    if update_status:
        # Update experiment status to show that its deleted
        experiment.set_status(ExperimentLifeCycle.DELETED)
