### v1.0.2 (development)
- DONE - incorporate more dockers and fix the issues to connect. I think we are obligating the environment variable to be setup. maybe we need to insert in .env, gitingore and put a message that needs to be setup the first time. maybe there are other options.
- DONE - mcp-server is not starting correctly and in the logs show that "requests" is not found. I need to debug because now it should be in the pyproject.toml and after doing task build does not show any error.
- DONE - start migrating audioserver so it can be run from tasks in ermes-stack
- DONE - hacer que task logs me permita filtrar por los logs de audioserver
- DONE - hacer que task status me permita ver tambien el audioserver. igual audioserver tendria que mostrarse en minusculas.
- DONE - testear task build con audioserver
- DONE - luego mirar el servicio de aina
- DONE - arrancar el servicio del modelo con llama-cpp
- DONE - tinc que determinar si el RouterAgent es realitat algo que es te que instanciar amb el orchestrator o es independent.
- DONE - falta acabar de arreglar el audioctl perque sigui mes robust. 
- DONE - tenemos un error en audioserver. no muestra suficientes logs y los logs que muestra no son buenos.
- DONE - el mcp falla perque no te els intents. haig de fer una mica solida aquesta situació: s'ha de fer un script de init? hauria de fallar el mcp sino te intents?
- DONE - mirar de generar logs al cli, perque no se si falla que pot ser i vull alguna forma facil de generarlos tipus "task". com que es un cli ho haig de pensar.
- DONE - despres d'aixo lo seu seria veure si puc fer sonar la veu de la resposta. ja funciona la veu. He trobat diversos problemes: la configuracio config.json no era la correcta. no hi habia una forma de comprobar-ho. el audioserver apuntaba a una ruta antiga i al recompilar hi havia 2 processos audioserver.
- DONE - intentar que el audioctl detecti si hi ha mes de un audioserver corrent com a process i escoltant al mateix port i m'avisi. no se si fer que mati l'antic process. potser es que no es el mateix arrancar un process desde de windows que des de linux.
- DONE - fer que el commandline retorni amb streaming i no fins que s'esperi la frase completa.
- DONE - pensar un sistema per actualitzar la vector database que tingui sentit. començar a fer-la servir per enrutar cap als correspondents agents.
- sembla que l'enrutat a un intent en concret no està funcionant. M'haig d'assegurar que enruta be i el intent funciona be. Començar per el de la hora.
- Moure els scripts de intent clasification o al orchestrator o al stack. Crec que es millor moure-ho al stack.
- migrar el task devices al audioctl, i treure l'script de windows.


- migrar assistant. el orchestrator esta restarting. estic deprecant sounddevice library i he trobat que hi ha 3 possibles candidats a deprecar: recording.py
simulstreaming_whisper_server.py
whisper_streaming/whisper_server.py

