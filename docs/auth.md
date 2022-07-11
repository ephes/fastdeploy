# Authentication / Authorization

Authentication and authorization are both handled by providing
an auth token in the request header. Authorization is checked
by having to provide different token types for different endpoints.

## Access Token

To obtain an access token you have to post `username` and `password`
to the `/token` endpoint. This is used by logged in useres of the Vue frontend to access the API do to things like:

* Fetch the list of services
* Obtain a service token
* ...

## Service Token

This token is used to start a deployment for a service.

An example workflow would look like this:
* A user logged in to the vue frontend uses it's access token to get a service token
* He stores this service token in the `secrets` section of a GitHub repository
* This service token is then used to start a deployment for a service after a successful push to the main branch of the repository

## Deployment Token

Deployment tokens are generated when a service is getting deployed.
The deployment process, which is completely separate from the
application server, is provided with a deployment token via its
environment. The deployment process is now able to use its token
to send back information about steps to process and finish the
running deployment.

## Config Token

There are some services like logging, monitoring or backup which
need access to the configuration of deployed services. The need
a config token to obtain the list of configurations for all deployed
services
