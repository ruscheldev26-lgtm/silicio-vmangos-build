-- Run ONLY on a disposable database named silicio_test_characters.
-- First create Silicio normally in the 4449 client: male gnome mage, level 1.
DELIMITER //
CREATE PROCEDURE silicio_test_register()
BEGIN
  DECLARE n INT DEFAULT 0;
  IF DATABASE() <> 'silicio_test_characters' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Refusing non-test database';
  END IF;
  SELECT COUNT(*) INTO n FROM characters WHERE name='Silicio' AND race=7 AND class=8 AND level=1 AND xp=0;
  IF n <> 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Create exactly one fresh level-1 gnome mage Silicio normally';
  END IF;
  IF EXISTS (SELECT 1 FROM playerbot p JOIN characters c ON c.guid=p.char_guid WHERE c.name='Silicio') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Silicio is already registered; inspect instead of overwriting';
  END IF;
  INSERT INTO playerbot (char_guid,chance,ai) SELECT guid,0,'SilicioAI' FROM characters WHERE name='Silicio';
END//
DELIMITER ;
CALL silicio_test_register();
DROP PROCEDURE silicio_test_register;
