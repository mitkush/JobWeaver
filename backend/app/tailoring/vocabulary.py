"""Technologies the truthfulness check looks for in AI output (ADR-0005).

Any of these named in a Draft must be in the User's Fact Bank. The Job's own required
skills and the alias table in skills.py are added at check time, so this list only needs
the common names an AI might add on its own. Lower case, comma-separated.
"""

_RAW = """
python, java, javascript, typescript, go, rust, ruby, php, c#, c++, kotlin, swift, scala,
elixir, erlang, haskell, clojure, perl, matlab, dart, lua, objective-c, bash, powershell,
sql, graphql, react, angular, vue, svelte, next.js, nuxt, remix, redux, jquery,
tailwind css, bootstrap, html, css, sass, node.js, express, nestjs, deno, django, flask,
fastapi, rails, ruby on rails, spring, spring boot, laravel, symfony, .net, blazor,
phoenix, hibernate, postgresql, mysql, mariadb, sqlite, oracle, sql server, mongodb, redis,
cassandra, dynamodb, elasticsearch, opensearch, neo4j, couchbase, cockroachdb, clickhouse,
snowflake, google bigquery, redshift, databricks, supabase, firebase, firestore, memcached,
kafka, rabbitmq, activemq, nats, pulsar, kinesis, sqs, celery, airflow, dagster, prefect,
spark, hadoop, flink, apache beam, dbt, pandas, numpy, scipy, scikit-learn, pytorch,
tensorflow, keras, jax, hugging face, langchain, llamaindex, mlflow, kubeflow, xgboost,
lightgbm, opencv, spacy, nltk, docker, kubernetes, helm, terraform, pulumi, ansible, chef,
puppet, vagrant, packer, aws, gcp, azure, aws lambda, ec2, s3, ecs, eks, fargate,
cloudformation, cloud run, gke, aks, heroku, vercel, netlify, cloudflare, digitalocean,
jenkins, github actions, gitlab ci, circleci, travis ci, argo cd, spinnaker, prometheus,
grafana, datadog, new relic, splunk, sentry, opentelemetry, jaeger, kibana, logstash,
nginx, haproxy, envoy, istio, linkerd, consul, webpack, vite, babel, jest, vitest, mocha,
cypress, playwright, selenium, pytest, junit, grpc, rest, websocket, oauth, jwt, saml,
ios, android, flutter, react native, xamarin, unity, unreal engine, solidity, ethereum,
tableau, power bi, looker, salesforce, sap, shopify, wordpress, linux, microservices,
serverless, event sourcing, cqrs, ci/cd, devops, mlops, machine learning, deep learning,
natural language processing, computer vision, large language models
"""

TECHNOLOGIES: frozenset[str] = frozenset(
    term.strip() for term in _RAW.replace("\n", " ").split(",") if term.strip()
)
