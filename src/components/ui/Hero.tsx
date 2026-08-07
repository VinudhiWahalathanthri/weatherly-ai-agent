import React from "react";

import { motion, useMotionValue, useTransform } from "framer-motion";

const Hero: React.FC = ({}) => {
  return (
    <>
      <section
        id="home"
        className="relative w-full h-screen flex items-center justify-center"
      >
        <div className="absolute inset-0 ">
          <img
            src="src/assets/image.png"
            alt="Earth"
            className="w-full h-full object-cover object-top"
          />
          <div className="absolute inset-0 bg-black/45" />
        </div>
        <motion.div
          className="relative z-10 space-y-3 flex flex-col mt-10 items-center lg:items-start md:px-40"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 1 }}
        >
          <span className="text-4xl md:text-7xl font-bold leading-none ">
            Weatherly
          </span>
          <motion.span
            className=" block text-white text-md md:text-xl lg:text-2xl font-bold"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5, duration: 0.8 }}
          >
            Becuase a perfect day deserves a perfect forecast
          </motion.span>
          <motion.div
            className="flex items-center  gap-4 mt-5"
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.7, duration: 0.8 }}
          >
            <motion.span className="text-md md:text-xl ps-4 pr-4 lg:ps-1 text-white text-center lg:text-start leading-relaxed ">
              Weatherly is a modern, intuitive web application that delivers
              precise and up-to-date weather information directly from{" "}
              <span className="text-yellow-500">NASA’s </span>
              datasets. Whether you’re planning your day, tracking climate
              trends, or just curious about the skies.
            </motion.span>
          </motion.div>
          <motion.button
            className="px-7 py-3 mt-10"
            style={{
              backgroundColor: "#87D0FF",
              borderRadius: 20,
              boxShadow: "0px 4px 4px rgba(255, 255, 255, 0.4)",
              cursor: "pointer",
            }}
            whileHover={{ scale: 1.05 }}
            onClick={() => {
              const element = document.getElementById("weather");
              const navbarHeight =
                document.querySelector("nav")?.offsetHeight || 0;
              const topPosition =
                element.getBoundingClientRect().top +
                window.pageYOffset -
                navbarHeight;

              window.scrollTo({
                top: topPosition,
                behavior: "smooth",
              });
            }}
          >
            <span
              style={{
                fontFamily: "Lato",
                fontWeight: "bold",
                fontSize: 17,
                color: "black",
              }}
            >
              Start Planning your day
            </span>
          </motion.button>
        </motion.div>
      </section>
    </>
  );
};

export default Hero;
