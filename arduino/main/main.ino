char buffer = 0;

void setup()
{
  pinMode(13, OUTPUT);
  Serial.begin(115200);
}

void loop()
{
  if (Serial.available() > 0) {
    buffer = Serial.read();
    Serial.print("I received: ");
    Serial.println(buffer, DEC);
    if(buffer == 'a') {
      digitalWrite(13, HIGH);
    }
    else if(buffer == 'b') {
      digitalWrite(13, LOW);
    }
  }
}
