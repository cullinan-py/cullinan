from .root import describe, main

if __name__ == "__main__":
    print("resolved configuration (base):")
    for key, value in describe().items():
        print(f"  {key}: {value}")
    print("resolved configuration (profile='prod'):")
    for key, value in describe(profile="prod").items():
        print(f"  {key}: {value}")
    main()
