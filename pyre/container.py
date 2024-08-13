from dependency_injector import containers, providers
import logging


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()
    logger = providers.Resource(logging.getLogger, name=config.logger.name)

    service = providers.Factory(Service, database=database)
    controller = providers.Factory(Controller, service=service)

    api = providers.Factory(API, controller=controller)
    web = providers.Factory(Web, api=api)
    app = providers.Factory(App, web=web)
