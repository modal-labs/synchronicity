import two_way_generator

# sync tests
gen = two_way_generator.echo_generator()

gen.send(None)  # type: ignore  # First send must be None, even though signature specifies str
gen.send("hello")  # str send values


async def async_check():
    agen = two_way_generator.echo_generator.aio()

    await agen.asend(None)  # type: ignore  # First send must be None, even though signature specifies str
    await agen.asend("hello")  # str send values
