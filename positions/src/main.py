import logging
import time
from src.consumer import receive_batch, delete_batch, deduplicate
from src.database.repository import upsert_positions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    logger.info("positions consumer iniciado")
    while True:
        try:
            messages = receive_batch()
            if not messages:
                continue

            positions = deduplicate(messages)
            upsert_positions(positions)
            delete_batch(messages)

            logger.info(f"{len(messages)} mensagens → {len(positions)} escritas no DynamoDB")

        except Exception as e:
            logger.error(f"erro no ciclo: {e}")
            time.sleep(2)


if __name__ == "__main__":
    main()