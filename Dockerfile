# One image for every use case: Lambda runs pkvai.handler.lambda_handler, Fargate runs the same code as a worker.
FROM public.ecr.aws/lambda/python:3.13
COPY pyproject.toml ${LAMBDA_TASK_ROOT}/
COPY src ${LAMBDA_TASK_ROOT}/src
COPY config ${LAMBDA_TASK_ROOT}/config
COPY prompts ${LAMBDA_TASK_ROOT}/prompts
RUN pip install --no-cache-dir "${LAMBDA_TASK_ROOT}[aws]" && rm -rf ${LAMBDA_TASK_ROOT}/config/world.toml ${LAMBDA_TASK_ROOT}/config/heldout.toml
CMD ["pkvai.handler.lambda_handler"]
