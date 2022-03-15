# Endpoints

Just a note to myself which endpoints have to write / fetch which data from the database.

# default

## read_users_me /users/me

Auth: Fetches the current user from database via `uow.users.get(username)`.

Expects an access token and returns the current user.

## login_for_access_token /token

Auth: Fetches the current user from database via `uow.users.get(username)`.

Receives username and password via post and returns an access token.

Both endpoints above should use the same get user function from views.

## service_token /service-token

Auth: Fetches the current user from database via `uow.users.get(username)`.

Receives a service_name, origin and expiration in days number via post and returns a signed service token.

# steps

## get_steps_by_deployment /steps/

Auth: Fetches the current user from database via `uow.users.get(username)`.

Reads from database:
* Fetches a deployment via `uow.deployments.get(deployment_id)`
* Fetches a list of steps via `uow.steps.get_steps_from_deployment(deployment_id)`

## process_step_result /steps/

Auth: Fetches the current deployment from database via `uow.deployments.get(deployment_id)`

Reads from database:
* Fetches a deployment via `uow.deployments.get(deployment_id)`
* Fetches a list of steps via `uow.steps.get_steps_from_deployment(deployment_id)`

Hmm, auth + those fetches can be done in the same function.

Writes to database:
* Saves a list of updated steps via `uow.steps.add(step)`

# services

## get_services /services/

Auth: Fetches the current user from database via `uow.users.get(username)`.

Reads from database:
* Fetches all services from database via `uow.services.list()`

## delete_service /services/{service_id}

Auth: Fetches the current user from database via `uow.users.get(username)`.

Reads from database:
* Fetches the service to delete from database via `uow.services.get(command.service_id)`

Writes to database:
* Deletes service from database via `uow.services.delete(service)`

This might delete deployments and steps via on_cascade, too.

## get_service_names /services/names/

Auth: Fetches the current user from database via `uow.users.get(username)`.

Fetches list of available service names from filesystem via:
* `fs.list()`

## sync_services /services/sync

Auth: Fetches the current user from database via `uow.users.get(username)`.

Reads from database:
* All services from database via `uow.services.list()`
* All services from filesystem via `fs.list()`

Writes to database:
* Delete one or more services via `uow.services.delete(to_delete)`
* Update/Add one or more services via `uow.services.add(to_update)`

# deployments

## get_deployments /deployments/

Auth: Fetches the current user from database via `uow.users.get(username)`.

Reads from database:
* Get a list of all deployments via `uow.deployments.list()`

## get_deployment_details /deployments/{deployment_id}

Auth: Fetches the current service from database via `uow.services.get_by_name(servicename)`.

Reads from database:
* Fetches a deployment via `uow.deployments.get(deployment_id)`
* Fetches a list of steps via `uow.steps.get_steps_from_deployment(deployment_id)`

## finish_deployment /deployments/finish/

Auth: Fetches the current deployment from database via `uow.deployments.get(deployment_id)`

Reads from database:
* Fetches the current deployment again via `uow.deployments.get(command.deployment_id)`
* Fetches the list of deployment steps via `uow.steps.get_steps_from_deployment(command.deployment_id)`

This could be done via `views.get_deployment_with_steps`.

Writes to the database:
* Updates the finished timestamp on deployment via `uow.deployments.add(deployment)`
* Deletes a list of steps via `uow.steps.delete(step)`

## start_deployment /deployments/

Auth: Fetches the current service from database via `uow.services.get_by_name(servicename)`.

Reads from database:
* Fetches current service from database again via `uow.services.get(command.service_id)`
* Get last successful deployment id from database via `uow.deployments.get_last_successful_deployment_id(service.id)`
* Fetches a list of steps from database via `uow.steps.get_steps_from_deployment(last_successful_deployment_id)`
*

Writes to database:
* Create a new deployment via `uow.deployments.add(deployment)`
* Create pending steps (who need a deployment_id) via `uow.steps.add(step)`
