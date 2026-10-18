### v1.0.2 (development)
- DONE - incorporate more dockers and fix the issues to connect. I think we are obligating the environment variable to be setup. maybe we need to insert in .env, gitingore and put a message that needs to be setup the first time. maybe there are other options.
- DONE - mcp-server is not starting correctly and in the logs show that "requests" is not found. I need to debug because now it should be in the pyproject.toml and after doing task build does not show any error.
- DONE - start migrating audioserver so it can be run from tasks in ermes-stack
- DONE - hacer que task logs me permita filtrar por los logs de audioserver
- DONE - hacer que task status me permita ver tambien el audioserver. igual audioserver tendria que mostrarse en minusculas.
- DONE - testear task build con audioserver
- DONE - luego mirar el servicio de aina
- arrancar el servicio del modelo con llama-cpp